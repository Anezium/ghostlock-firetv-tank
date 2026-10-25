# Fire TV Stick 2 (AFTT / tank) — audit root & fluidité

Date : 2026-10-25 · Appareil : AFTT / tank, Fire OS 5.2.9.5 (`288.6.8.8_user_688805020`)
Fire OS **5.2.9.5 (688805020)** · Android 5.1.1 · noyau **3.10.54+** (build 2024-03-13) · ARM 32 bits · SELinux **Enforcing** · patch déclaré `2022-00-01`

## 1. Accès

| Élément | État |
|---|---|
| ADB | OK, uid **2000 (shell)**, pas de `su` |
| `ro.build.type` / `ro.debuggable` | `user` / `0` → `adb root` impossible |
| `pm disable-user` / `pm hide` | **bloqués** (`SecurityException` uid 2000) |
| `pm uninstall --user 0` (app système) | « Success » mais ne retire que la mise à jour `/data/app` |
| `settings put global` | autorisé |

Conclusion : aucun levier de désactivation d'applis système sans root sur ce build.

## 2. Failles noyau

### Dirty COW — CVE-2016-5195 : **corrigé**
Le correctif est présent dans le binaire (`kernel-688805020.elf`, `follow_page_mask` @ `0xc0117570`) :

```
ands r10, r4, #1          ; FOLL_WRITE
tst  r3, #128             ; L_PTE_WRITE
movw r2, #0x4010          ; FOLL_FORCE | FOLL_COW
and  r2, r4, r2
cmp  r2, r1               ; exige FOLL_FORCE + FOLL_COW
ands r9, r3, #64          ; L_PTE_DIRTY
```
→ logique `can_follow_write_pte()` patchée (identique à `source-subset/memory.c:1474`).
Confirmé côté appareil : `safe_probe` ne reproduit pas la faille.

### GhostLock / CVE-2026-43499 (IonStack, futex-PI UAF) : **VULNERABILITE PRESENTE**

Correction d'une conclusion antérieure. GhostLock *l'outil* ne supporte que la famille
`sheldon` (Fire TV Stick 3 / Lite 2020, Fire OS 7, noyaux 4.4/4.14/5.10) — mais la
**vulnérabilité sous-jacente n'est pas liée à ces noyaux**.

Fiche CVE-2026-43499 : « rtmutex: Use waiter::task instead of current in remove_waiter() ».
Plages affectées : **à partir de 2.6.39** jusqu'à 5.10.260 / 5.15.211 / 6.1.174 / 6.6.139 /
6.12.85 / 6.18.26 / 7.0.3. La branche 3.10 étant EOL, elle **ne recevra jamais le correctif**.

Vérifications sur ce firmware précis :

1. **Source** (`kernel/rtmutex.c`) : `remove_waiter()` fait
   `raw_spin_lock_irqsave(&current->pi_lock, flags)` puis
   `current->pi_blocked_on = NULL` — au lieu de `waiter->task`. Or il est appelé en
   rollback depuis `rt_mutex_start_proxy_lock()`, lui-même atteint par
   `futex_requeue()` sur `FUTEX_CMP_REQUEUE_PI` (`kernel/futex.c:1568`).
2. **Binaire 2024-03-13** : `remove_waiter` @ `0xc07069ec` calcule `current` depuis SP
   (`bic r8, r3, #8128` → `thread_info`), verrouille `current->pi_lock` (`[r10,#0xc]`
   puis `+1136+4`) et dépile sous ce verrou. Même code vulnérable.
3. **Déclencheur** : `futex(FUTEX_CMP_REQUEUE_PI)` est non privilégié. `safe_probe` a déjà
   confirmé que les opérations futex PI passent (uid 2000).

Conséquences du bug (CVE) : déqueue rbtree sans `waiter::task::pi_lock`, `pi_blocked_on`
non remis à zéro → **pointeur pendant → UAF**, et `rt_mutex_adjust_prio_chain()` sur le
mauvais waiter.

Ce qui manque pour un root : un portage de l'exploit (IonStack) vers 3.10 ARM32 — les
structures `rt_mutex_waiter` / `futex_q` / `task_struct` diffèrent, le reclaim se fait via
ION, puis il faut la reprise de contrôle ARM32 et le contournement SELinux. Aucun portage
public pour `tank`.

### Verdict (corrigé)
**La vulnérabilité existe et est atteignable sur cet appareil.** Il n'existe en revanche
aucun exploit public fonctionnel pour `tank`/3.10.54 : la faille est un point de départ,
pas un root clé en main. Le noyau de mars 2024 intègre les correctifs des failles
historiques d'Android 5.1, mais pas celui-ci (publié en 2026, branche morte).

Correction également : un oops avec `panic_on_oops=1` provoque un **reboot**, pas une
brique. La brique supposerait une écriture fiable dans les partitions — pas un simple crash.

Dossier complet (CVE, preuves, mécanique de l'UAF, conditions de déclenchement, ce qui
reste non établi) : `NOTE-CVE-2026-43499-tank.md`.

## 3. Fluidité — mesures

| Mesure | Valeur |
|---|---|
| RAM totale / libre | 895 Mo / ~76–124 Mo dispo |
| ZRAM | 72 Mo physiques pour 168 Mo de swap |
| Températures | **91 °C** (zone0), 76 °C, 78 °C |
| IOW | jusqu'à **35 %** (eMMC + swap) |
| Top CPU | Photos, Prime Video, launcher, system_server |

Le throttling thermique est probablement le premier facteur de lenteur, avant les applis.

## 4. Actions réalisées

- Animations système passées à **0.5** (`window_animation_scale`, `transition_animation_scale`, `animator_duration_scale`).
- `am force-stop` sur Photos / Vizzini / Screensaver : IOW 35 % → 1 %, CPU système 37 % → 22 % (temporaire, les services redémarrent).
- Amazon Photos : mise à jour `/data/app` retirée par le test `pm uninstall --user 0` (retour à la version système, aucune perte de données).

## 4 bis. Diff contre l'upstream Linux 3.10

Arbre vendor extrait de `platform.tar` : **5 959 fichiers, 55 Mo** (`kernel/mediatek/mt8127d/3.10`), avec `tank_defconfig`.
Baselines : `linux-3.10.54` (base BSP) et `linux-3.10.108` (dernier de la branche).

62 fichiers sensibles comparés (`upstream-diff.txt`) :

- **17 identiques à 3.10.54** → aucun correctif stable depuis 2015 :
  `kernel/ptrace.c`, `kernel/cred.c`, `kernel/user.c`, `kernel/groups.c`,
  `mm/msync.c`, `fs/read_write.c`, `fs/splice.c`, `fs/dcache.c`, `fs/namei.c`,
  `fs/open.c`, `fs/fcntl.c`, `fs/notify/inotify/inotify_fsnotify.c`,
  `ipc/msg.c`, `ipc/sem.c`, `ipc/util.c`, `net/core/skbuff.c`, `drivers/char/random.c`.
- **5 identiques à 3.10.108** (à jour) : `kernel/cred.c`, `mm/msync.c`, `fs/read_write.c`, `fs/fcntl.c`, `fs/notify/inotify/inotify_fsnotify.c`.
- Le reste est **partiellement** patché : Amazon a cherry-pické au cas par cas
  (`fs/pipe.c`, `kernel/futex.c`, `mm/memory.c` sont proches de 3.10.108 ;
  `mm/mmap.c` +131/-124, `fs/proc/task_mmu.c` +119/-14, `ipc/sem.c` +16/-35 restent en retard).

Conclusion : le noyau n'est ni « à jour », ni « figé en 2015 » — c'est un patchwork.
Il reste donc mécaniquement des correctifs upstream absents, mais aucun ne se traduit
directement en exploit : chaque CVE demande une vérification de reachability.

## 4 ter. Surface non couverte par le diff : le code vendor MediaTek

`/dev/mali` et `/dev/ion` sont en **0666**, et les drivers correspondants sont
100 % vendor, sans équivalent upstream :

- `drivers/misc/mediatek/gpu/mt8127/mali/` (Mali-450 Utgard, gros bloc ioctl)
- `drivers/staging/android/ion/` (variante MTK, `CONFIG_ION_MTK=y`)
- `drivers/misc/mediatek/gpu/ged/`, vcodec, `CONFIG_MTK_EMI_MPU=y`

C'est là que se trouverait un bug non patché, pas dans les fichiers cœur déjà connus.

Éliminé d'office par la config : `CONFIG_MTK_CMDQ` **non activé** (donc CVE-2020-0069 /
mtk-su hors jeu), `keyctl` absent, pas de user namespaces, pas d'eBPF/io_uring (inexistants en 3.10),
pas de `pkexec` (donc CVE-2019-13272 non reachable).

## 4 quater. Audit de surface userspace (21 paquets uid 1000)

- **AF_PACKET refusé** par SELinux depuis le shell : `errno 13` en SOCK_RAW et SOCK_DGRAM
  → toute la famille « socket brut » (CVE-2017-7308…) est hors d'atteinte depuis ADB.
  `AF_NETLINK` reste autorisé.
- ~40 composants « exportés sans permission » au premier filtre, mais :
  - la majorité sont des receivers de **broadcasts protégés** (`BOOT_COMPLETED`,
    `CONNECTIVITY_CHANGE`, `PACKAGE_CHANGED`) → non déclenchables par une app tierce ;
  - les providers sérieux ont des **contrôles code** : `UnifiedSettingsProvider`
    (`com.amazon.CONTENT_PROVIDER_ACCESS`), `CredentialStorageMapInfoProvider`
    (`CAN_CALL_MAP_INFORMATION_PROVIDER`), `SaleProvider` (`ACCESS_SALE_PROVIDER`).
- **Un seul réellement joignable** : `content://com.amazon.platform.fdrw` (uid 1000).
  `content query` → `NullPointerException: storage == null`, mais
  `content call --method ping` → **Bundle accepté** depuis uid 2000.
  Lecture non protégée, écriture réservée à `com.amazon.platform.fdrw.permission.RW_OWN`.
- **ION** : garde-fou `_IOC_SIZE(cmd) > sizeof(data)` présent → pas d'écrasement de pile
  par taille d'ioctl. **Mali Utgard** : gros bloc ioctl, non audité en profondeur.

## 4 quinquies. `com.amazon.platform.fdrw` — bug réel, pas un root

L'APK ne contient aucun `classes.dex` : le code est AOT-compilé dans
`/system/app/fdrw/arm/fdrw.odex` (45 Ko). Dex extrait de l'odex, puis désassemblé (`dexdump`).

Trois classes : `Provider`, `Provider$DatabaseOpener`, `PackageWhitelistingHandler`.

**Défaut confirmé** — `Provider.call(method, arg, extras)` ne vérifie aucune permission :

```
if ("updatePackagePath".equals(method)) {
    pkg  = extras.getString("packageName");
    path = extras.getString("sourceDir");
    updatePackagePath(pkg, path);          // aucun contrôle d'appelant
}
```

et `updatePackagePath` fait ensuite :

```
ownerKey = "fdrw:" + pkg;                                   // contrôlé par l'appelant
deleteItemsForPackage(null, null, ownerKey);
    -> String.format("%s = \"%s\"", "owner", ownerKey)       // concaténation SQL
    -> db.delete("items", selection, null)
db.insert("items", null, {priority=0, owner=ownerKey, path=path});
```

→ **injection SQL** dans la clause `WHERE`, et écriture d'une ligne arbitraire
(`owner`, `path`) dans la base du provider, **en uid 1000** (`android.uid.system`),
depuis n'importe quelle app ou depuis ADB shell.

**Portée réelle** : la base visée est celle du provider (`items`). Pas de chemin vers
`uid 0` démontré. L'intérêt dépend d'un consommateur privilégié qui ferait confiance à
ces `path` pour accorder un droit — non prouvé à ce stade. C'est un défaut
d'intégrité / déni de service dans une app système, pas une élévation de privilèges.

À noter : `query` échoue en `NullPointerException: storage == null` sur ce build,
ce qui suggère un provider partiellement cassé — ce qui limite aussi l'exploitation.

## 5. Pistes restantes sans root

1. Désinstaller les applis **utilisateur** inutiles (ça, c'est autorisé).
2. `am force-stop` des services Amazon avant une session (script PC).
3. Rafraîchir : vider les caches des applis de streaming.
4. **Physique** : rallonge HDMI pour dégager le stick, aération — viser < 70 °C.
5. Changer d'accueil : impossible sans désactiver le launcher Amazon (root requis).
