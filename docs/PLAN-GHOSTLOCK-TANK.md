# GhostLock `tank` — plan V1 (CLI PC, root one-shot)

Statut : **V1 fonctionnelle** — root one-shot obtenu (`uid=0`, `u:r:kernel:s0`,
SELinux permissive) via un hijack `ashmem_misc.fops`, avec CLI PC, garde de build,
nettoyage du fd et reprise automatique après échec. Fiabilité mesurée et limite
connue en fin de document.
Périmètre : Fire TV Stick 2 `AFTT` / `tank`, Fire OS 5.2.9.5, build
`288.6.8.8_user_688805020`, noyau 3.10.54+ (2024-03-13), ARM32 MT8127.

## Objectif

Un root **temporaire, one-shot, rejouable**, piloté depuis le PC en ADB, sur un
stick stock (sans aiguille, sans recovery, sans déverrouillage). Pas de daemon,
pas d'APK, pas de persistance : la V1 s'arrête à « j'obtiens uid 0 dans une
session, de façon fiable et mesurée ».

Hors périmètre V1 : root à chaque boot, manager `su`, application Android,
publication d'un one-click.

## Utilisation

```
python scripts/gl_bench.py --serial 192.168.1.172:5555 doctor
python scripts/gl_root.py  --serial 192.168.1.172:5555 --cmd "id; getenforce"
```

`gl_root.py` :

1. garde de build (`288.6.8.8_user_688805020`, `tank`, `3.10.54`) ;
2. pousse `probes/gl_exploit`, `sync`, vérifie la taille sur l'appareil ;
3. lance le payload en **uid 2000** (`shell`), une tentative = un processus neuf ;
4. détecte le succès par un marqueur émis par le shell root
   (`echo GL_ROOT_OK; <commande>; echo GL_DONE:$?`), donc un échec silencieux
   n'est jamais pris pour un succès ;
5. en cas d'échec, reboot propre puis nouvelle tentative (jusqu'à `--attempts`,
   défaut 3) ; après un panic, attend simplement le retour du boot.

## Contrat de fiabilité

| Critère | Cible | Mesure |
|---|---|---|
| Succès | ≥ 95 % en ≤ 3 tentatives | campagnes ci-dessous |
| Échec | reboot propre, aucune écriture persistante | `last_kmsg` + partitions inchangées |
| Signature | même adresse fautive à chaque crash | parsing automatique |
| Build | refus si ≠ `688805020` / `tank` / `3.10.54` | garde dans `gl_bench.py` |
| Temps | < 2 s hors reboot | horodatage du run |

## Ce qui est déjà en place

### Boîte noire (validée)

`/proc/last_kmsg` n'est pas le log courant : c'est un **snapshot du boot
précédent**, copié à `console_initcall` par
`drivers/misc/mediatek/ram_console/mtk_ram_console.c`. Il contient donc le log
complet du boot qui a crashé, y compris l'oops et sa backtrace, et il est stable
(kmalloc, pas le ring buffer live).

Preuve : après un `adb reboot`, le hook a créé
`/data/local/tmp/gl/runs/boot-20100101-000002-2/` contenant 405 366 octets de
log du boot précédent, terminé par `Restarting system`.

Hooks installés (Magisk 23, aucun accès partition) :

- `/data/adb/post-fs-data.d/99-gl-blackbox.sh` : copie `last_kmsg`, props,
  version noyau, cmdline, SELinux, `panic_on_oops`, `kptr_restrict`, et rattache
  le marqueur `pending` du run en cours.
- `/data/adb/service.d/99-gl-late.sh` : marqueur `boot_ok.txt` (uptime).

Le répertoire de travail `/data/local/tmp/gl` est volontairement **owned by
shell** (777) : le payload uid 2000 doit pouvoir y écrire, et `adb push` doit y
fonctionner. Root peut toujours y écrire (vérifié).

### Banc PC

`scripts/gl_bench.py` (stdlib seulement) :

```
python scripts/gl_bench.py doctor
python scripts/gl_bench.py install
python scripts/gl_bench.py snapshot --label baseline
python scripts/gl_bench.py run --payload probes/gl_exploit --arg 1
python scripts/gl_bench.py runs
```

Chaque run :

1. vérifie le build (sinon refus) ;
2. pousse le payload et un `cmd.sh` dans `/data/local/tmp/gl` ;
3. écrit `pending` (id, sha256, args, date) ;
4. exécute **en uid 2000** (`--root` réservé aux helpers de labo) ;
5. attend le retour ou le reboot, compare l'uptime pour distinguer les deux ;
6. récupère le répertoire du run et le boot dir contenant `pending.json` ;
7. parse `last_kmsg` (fault addr, oops code, PC, LR, panic), écrit
   `analysis/gl-runs/<id>/summary.json` + `index.jsonl`.

### Pièges rencontrés (à garder)

- `adb shell su -c "cmd1; cmd2 > file"` fait ré-évaluer les métacaractères par
  le shell **externe** (uid 2000). Toujours pousser un script et faire
  `su -c 'sh /chemin/script.sh'`.
- `dmesg` est refusé même en root (`klogctl: EPERM`). Toute la télémétrie passe
  par `last_kmsg`.
- `kptr_restrict=2` : adresses masquées dans `/proc/kallsyms`. Les adresses
  statiques viennent de `firmware/kernel-688805020.elf` (pas de KASLR).
- `panic_on_oops=1` : tout oops = reboot immédiat. C'est le comportement
  attendu du banc, pas un bug.
- **`adb push` ne fait pas de fsync** : sans `sync` après le push, un panic
  immédiat laisse un binaire de **0 octet** sur `/data`, et la tentative
  suivante exécute du vide. `gl_root.py` fait `sync` puis vérifie la taille.

## Phase 1 — reproduire le build : **FAIT**

Le build complet `zImage` est bloqué par des fichiers absents de l'arbre vendor
pruned (`net/netfilter/xt_TCPMSS.c`, `include/linux/mali/mali_utgard_uk_types.h`),
mais ce n'est pas nécessaire. Les objets qui comptent se compilent avec la config
et le toolchain exacts :

```
make O=/tmp/tank-build ARCH=arm CROSS_COMPILE=/opt/arm-eabi-4.8/bin/arm-eabi- \
     kernel/rtmutex.o kernel/futex.o
```

Résultat décisif : `remove_waiter` compilé est **instruction pour instruction
identique** au binaire Amazon (`0xc07069ec`), aux relocations près. Le noyau
vendor a donc bien été produit avec cette source, cette config et GCC 4.8.

Offsets extraits du DWARF (validés par le désassemblage) :

| Structure | Champ | Offset |
|---|---|---|
| `rt_mutex_waiter` | `list_entry` | 0 |
| | `pi_list_entry` | 20 |
| | `task` | 40 |
| | `lock` | 44 |
| | taille | **48** |
| `futex_q` | `task` | 20 |
| | `pi_state` | 40 |
| | `rt_waiter` | 44 |
| | `requeue_pi_key` | 48 |
| `task_struct` | `cred` | 852 |
| | `real_cred` | 848 |
| | `comm` | 856 |
| | `pi_lock` | **1140** |
| | `pi_waiters` | 1144 |
| | `pi_blocked_on` | **1152** |

`pi_lock` à 1140 est exactement ce que fait le binaire (`add #1136` puis
`add #4`). La correspondance est donc fiable pour les autres champs.

## Phase 2 — déclencheur déterministe : **FAIT (200/200)**

`probes/gl_trigger.c` implémente la chaîne A/C/B et valide le chemin :

```
round: requeue=-1/35 wait=-1/110 c_lx=0/0 OK
RESULT ok=200 bad=0 rounds=200
```

Deux corrections importantes par rapport à l'idée initiale :

1. **`FUTEX_WAKE` ne peut pas libérer A** après le rollback : `futex_q.rt_waiter`
   est encore armé et `wake_futex()` refuse (`futex.c:954`, « refusing to wake
   PI futex »). A doit sortir par **timeout** (ou signal).
2. Le timeout de `FUTEX_WAIT_REQUEUE_PI` est **absolu** (`CLOCK_MONOTONIC`) en
   3.10, contrairement à `FUTEX_WAIT`. Un `{5,0}` est déjà dans le passé et
   renvoie `ETIMEDOUT` immédiatement.

Le handshake ne repose sur aucun `sleep` fixe : B lit
`/proc/self/task/<tid>/wchan` jusqu'à voir A dans `futex_wait_queue_me` et C
dans `rt_mutex_timed_lock` (ou le bit `FUTEX_WAITERS` sur `Lx`). C'est ce qui
rend les 200/200 reproductibles.

## Phase 3 — contrôle de pile : **FAIT**

- Buffer ashmem : `set_name()` copie 256 octets à `top-588`
  (`local_name[256]`, `ashmem_mutex` pris **après** la copie).
- `rt_waiter` réel : `local_name + 92` ; champ `lock` à `local_name + 136`.
- Offset mesuré par canaris uniques : faute à `0xf9013304` → mot 34 → `lock` à 136.
- Le filler doit écrire puis **ne plus faire de syscall** : un `pause()`/`schedule`
  écrase la pile. Le spin userspace, lui, garde le contenu.
- Canari : `Unhandled fault ... at 0xdeadbeef`, `PC = _raw_spin_trylock`.

## Phase 4 — écriture arbitraire, root et nettoyage : **FAIT**

Chaîne finale (`probes/gl_exploit.c`) :

1. A possède `Lx`, attend `FUTEX_WAIT_REQUEUE_PI(uaddr1 → L2)`, C possède `L2`
   et bloque sur `Lx`, B fait `FUTEX_CMP_REQUEUE_PI` → `-EDEADLK`.
2. Le rollback (`rt_mutex_start_proxy_lock` → `remove_waiter`, dans le contexte
   de B) retire le waiter de A de `L2` mais laisse `A->pi_blocked_on` pointer
   dessus.
3. A sort par timeout : `handle_early_requeue_pi_wakeup()` détecte le réveil
   précoce (`q->key` n'a pas été requeue) et **ne nettoie pas**
   `A->pi_blocked_on`.
4. A appelle `ioctl(ASHMEM_SET_NAME)` : `set_name()` copie 256 octets par-dessus
   le `rt_waiter` resté sur sa pile (faux `rt_mutex`, faux nœud `plist`), puis A
   tourne en userland **sans plus aucun syscall**.
5. B fait `FUTEX_LOCK_PI(Lx)` : `task_blocks_on_rt_mutex` →
   `rt_mutex_adjust_prio_chain` suit `A->pi_blocked_on` dans le faux waiter, et
   `plist_del()` fait l'écriture contrôlée `*(node_list.prev) = node_list.next`.
6. Cible : **`ashmem_misc.fops`** (`0xc0a137b4`) ← fausse table
   `file_operations` dans notre page (offset `open` = 44). B ouvre alors
   `/dev/ashmem` : `misc_open()` appelle `fake->open == kernel_payload`, dans
   **sa** tâche et **son** mm.
7. `kernel_payload` (SVC, pages user exécutables : pas de PXN sur MT8127) :
   - restaure `ashmem_misc.fops = ashmem_fops` (`0xc075fac0`) → fenêtre fermée
     au tout premier appel ;
   - repasse `file->f_op = def_chr_fops` (`0xc0724f18`), dont `flush`/`release`
     sont NULL : le fd factice devient inoffensif à la fermeture/au `exec` ;
   - `prepare_kernel_cred(current)` (copie **notre** blob SELinux valide, donc
     pas de dépendance à `init_cred.security`) ;
   - `uid/gid/euid/...= 0`, caps `permitted/effective/bset = ~0`, `sid = 1`
     (kernel) ;
   - `current->real_cred = current->cred = nouveau cred` ;
   - `selinux_enforcing = 0` (`0xc0ac66f0`) ;
   - retourne 0.

Résultat type :

```
B: ROOT uid=0 euid=0 open=4 errno=0 marker=41424344
uid=0(root) ... context=u:r:kernel:s0
Permissive
```

### Pourquoi cette cible

- Pas de table `security_ops` globale en mémoire utilisateur : un seul pointeur
  est détourné, et il est restauré par le premier appel.
- L'écriture et le déclenchement ont lieu dans **notre** tâche et **notre** mm :
  la page du payload est toujours mappée.
- L'ancienne cible `security_ops` cassait au bout de ~5 roots : les autres
  processus lisaient la table utilisateur dans leur propre mm
  (`selinux_file_open`, blob NULL).

## Fiabilité mesurée

| Campagne | Résultat |
|---|---|
| 40 rounds dans un processus (1re tentative) | **40/40** |
| 53 tentatives (campagne longue) | **48 root**, 4 échecs silencieux, 1 panic |
| CLI `gl_root.py`, 15 invocations | **15/15** à la 1re tentative |
| CLI `gl_root.py`, 12 invocations | **12/12** à la 1re tentative |
| **20 boots froids** (outil complet, ≤ 3 tentatives) | **20/20**, dont 4 avec une reprise |

Par tentative : ~**90–95 %** sur un système déjà chaud, ~**80 %** juste après un
boot (le système est plus chargé) ; ~2 % de panic. Avec la politique de reprise
(reboot propre + nouvelle tentative), l'outil a fait **20/20** sur des boots
froids réels.

Cause de la limite : entre le retour de l'ioctl (où le faux waiter est sur la
pile noyau de A) et le chain walk de B, A tourne en userland ; une préemption /
un tick peut empiler une frame de `schedule()` par-dessus le faux waiter. Selon
ce qui est écrasé, la tentative échoue silencieusement (le chain walk ne
reconnaît plus `next_lock`) ou panique (`_raw_spin_trylock` sur un `lock`
corrompu). C'est une fenêtre de quelques µs, mais le système est très chargé.

Politique de reprise :

- un échec silencieux laisse un état PI-futex pointant vers une tâche morte ;
  réutiliser le même noyau avec un nouveau processus peut entrer en collision
  (panic). `gl_root.py` **reboot proprement** avant chaque nouvelle tentative ;
- après un panic, il attend le retour du boot puis réessaie ;
- avec 3 tentatives, le taux de succès de bout en bout attendu est ≥ 99 %.

Piste pour supprimer la fenêtre (mesurée, non retenue) : faire bloquer A **dans**
`set_name()` en contention sur `ashmem_mutex` (A serait garé à `sp = top-588`,
sous le buffer, donc à l'abri des empilements). Mesure avec
`probes/gl_mutex_probe.c` : le seul hold déclenchable depuis userland est
`ashmem_mmap()` → `shmem_file_setup()`, qui ne tient le mutex que ~5–10 µs
(seuls ~1 % des `SET_NAME` dépassent 20 µs, max observé 7,8 ms). C'est trop
court pour un handshake fiable, et aucun autre chemin ashmem ne tient le mutex
assez longtemps. La piste restante serait un défaut de page **majeur** (I/O
eMMC) pendant le `strncpy_from_user` de `set_name()`, pour garer A plusieurs
millisecondes dans le noyau : faisable, mais nouveau chemin à valider.

## Règles de sécurité

1. Ne jamais écrire sur l'eMMC depuis l'exploit.
2. Garder le build guard : un offset faux sur une autre build = corruption.
3. Budget de tentatives + arrêt : pas de bootloop infini.
4. Tester sur le stick déjà rooté (labo, backups TWRP) avant tout stick stock.
5. La V1 ne promet pas la persistance : bootloader verrouillé + dm-verity.

## Reste à faire (hors V1)

- Supprimer la fenêtre de préemption (voir piste ci-dessus) pour viser > 99 %
  par tentative, sans reboot de reprise.
- Daemon/APK de persistance : nécessite une cible d'écriture persistante
  (dm-verity), hors périmètre.
