"""Preload approved images without creating or starting any servers."""
import argparse
from pathlib import Path
from engine import Engine,CATALOG,TEMPLATES

def main():
    p=argparse.ArgumentParser(description='Container-Abbilder vorladen (keine Serverinstallation).')
    p.add_argument('games',nargs='*',help='Vorlagen-IDs; siehe --list')
    p.add_argument('--all',action='store_true',help='Alle Abbilder laden; mehrere GB möglich')
    p.add_argument('--list',action='store_true')
    p.add_argument('--export',type=Path,help='Heruntergeladene Abbilder als Docker-TAR für Offline-Transfer speichern')
    p.add_argument('--import-file',type=Path,help='Zuvor exportierte Abbilder laden')
    args=p.parse_args();engine=Engine(Path(__file__).resolve().parent/'data')
    if args.list:
        for t in CATALOG:print(t['id']+' · '+t['name']+' · '+t['image'])
        return
    if args.import_file:
        if not args.import_file.is_file():p.error('Importdatei fehlt.')
        print(engine.docker('load','-i',str(args.import_file.resolve()),timeout=3600));return
    selected=list(TEMPLATES) if args.all else args.games
    if not selected:p.error('Vorlagen-IDs oder --all angeben; --list zeigt die Auswahl.')
    if any(k not in TEMPLATES for k in selected):p.error('Unbekannte Vorlage. --list zeigt die gültigen IDs.')
    for key in selected:
        print('Vorladen: '+TEMPLATES[key]['name'],flush=True)
        print(engine.docker('pull',TEMPLATES[key]['image'],timeout=1800),flush=True)
    if args.export:
        print('Abbilder exportieren …',flush=True)
        engine.docker('save','-o',str(args.export.resolve()),*[TEMPLATES[k]['image'] for k in selected],timeout=3600)
        print(str(args.export.resolve()))
    print('Fertig. Spieldateien können beim ersten Containerstart weitere Downloads benötigen.')

if __name__=='__main__':main()
