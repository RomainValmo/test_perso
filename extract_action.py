import json
import os

REPORT_FILE = "scan_report.json"
OUTPUT_FILE = "actions_list.txt"

def extract_actions():
    if not os.path.exists(REPORT_FILE):
        print(f"Erreur: Le fichier {REPORT_FILE} n'existe pas. Veuillez d'abord lancer le scan.")
        return

    with open(REPORT_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Erreur: Impossible de lire {REPORT_FILE}. Format JSON invalide.")
            return

    unique_actions = set()
    
    # Parcours des repos scannés
    if "scanned_repos" in data:
        for repo in data["scanned_repos"]:
            # Vérifie si le repo a des actions (le format a changé récemment, on gère les anciens formats au cas où)
            if isinstance(repo, dict) and "actions" in repo:
                for action_obj in repo["actions"]:
                    if "action" in action_obj:
                        unique_actions.add(action_obj["action"])

    # Tri pour l'affichage
    sorted_actions = sorted(list(unique_actions))

    print(f"Nombre d'actions uniques trouvées : {len(sorted_actions)}")
    print("-" * 40)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for action in sorted_actions:
            print(action)
            f.write(f"{action}\n")
            
    print("-" * 40)
    print(f"Liste sauvegardée dans {OUTPUT_FILE}")

if __name__ == "__main__":
    extract_actions()
