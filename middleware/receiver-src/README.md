# receiver-src — de solution waar de live receiver uit gebouwd wordt

Geëxporteerd van `mex-mw-01:/root/mex-middleware-b` (20-08-2026). Hiermee is
`Mex.Journal.Receiver` voor het eerst buiten de VPS te bouwen: `Mex.Journal.Recon`
(met `DiscordNotifier`) en `MexJournal.sln` ontbraken tot nu toe in git, waardoor
elke wijziging aan het live executiepad ongecompileerd de deur uit ging.

## Eén bron voor de receiver

`src/Mex.Journal.Receiver/Program.cs` zit **bewust niet** in deze map. De
authoritatieve versie is `middleware/dotnet-receiver/Program.cs`; twee kopieën
zouden precies de situatie maken die de werkafspraken verbieden. Kopieer hem
erin vóór het bouwen:

    cp middleware/dotnet-receiver/Program.cs \
       middleware/receiver-src/src/Mex.Journal.Receiver/
    dotnet build middleware/receiver-src/src/Mex.Journal.Receiver -c Release

**De receiver staat niet in `MexJournal.sln`.** Een kale `dotnet build -c Release`
meldt *Build succeeded* zonder hem te bouwen — dat heeft twee keer een deploy stil
laten mislukken. Bouw altijd het projectpad.

## Wat hier niet in staat

`mex-receiver.service` is een **sjabloon**. De draaiende unit bevat het webhook-secret
en de Discord-webhook-URL; die horen in `/etc/systemd/system/mex-receiver.service.d/env.conf`
op de VPS en niet in versiebeheer. De export van 20-08 bevatte ze wél — vandaar dat
beide op 25-08 geroteerd zijn.

`Program.cs.bak` is er ook uit; die stond op de 17-08-versie.
