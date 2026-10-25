param([Parameter(Mandatory=$true)][ValidateSet('Ready','Remove','Failure','Checked')][string]$Cue)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice('Microsoft Hortense Desktop')
    $speaker.Volume = 100
    $messages = @{
        Ready = 'Le script est pret. Attends le GO dans la conversation avant de brancher.'
        Remove = "Retire l'aiguille maintenant. Garde le cable USB branche. Retire seulement l'aiguille."
        Failure = "Le test est arrete. Debranche le cable USB puis retire l'aiguille."
        Checked = 'La lecture de la memoire fonctionne. Garde le cable USB branche. Tu peux poser tes mains.'
    }
    $speaker.Speak($messages[$Cue])
} finally {
    $speaker.Dispose()
}
