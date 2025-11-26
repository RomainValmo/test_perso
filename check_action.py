import os
import csv
import json
from github import Github, GithubException

# Configuration
GITHUB_TOKEN = "ton_github_token"
CSV_FILE = "list.csv"
ACTIONS_LIST_FILE = "actions_list.txt"
REPORT_FILE = "actions_scan_report.json"

def load_target_packages(filepath):
    packages = set()
    if not os.path.exists(filepath):
        print(f"Erreur: Le fichier {filepath} n'existe pas.")
        return packages
    
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                packages.add(row[0].strip())
    return packages

def load_actions_list(filepath):
    actions = set()
    if not os.path.exists(filepath):
        print(f"Erreur: Le fichier {filepath} n'existe pas. Lancez d'abord extract_actions.py")
        return actions
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('.') and not line.startswith('/'):
                # Nettoyage : on garde "owner/repo" et on retire "@version" ou "/subpath"
                # Ex: actions/checkout@v3 -> actions/checkout
                # Ex: owner/repo/path/to/action@v1 -> owner/repo
                
                # 1. Retirer la version
                base = line.split('@')[0]
                
                # 2. Garder uniquement owner/repo
                parts = base.split('/')
                if len(parts) >= 2:
                    repo_slug = f"{parts[0]}/{parts[1]}"
                    actions.add(repo_slug)
    return actions

def scan_external_actions():
    if not GITHUB_TOKEN:
        print("Erreur: Token GitHub manquant.")
        return

    g = Github(GITHUB_TOKEN)
    target_packages = load_target_packages(CSV_FILE)
    actions_repos = load_actions_list(ACTIONS_LIST_FILE)
    
    if not target_packages:
        print("Aucun package cible chargé.")
        return
    
    if not actions_repos:
        print("Aucune action à scanner.")
        return

    print(f"Scan de {len(actions_repos)} dépôts d'actions uniques...")
    
    report = {
        "scanned_actions": [],
        "matches": []
    }

    for repo_name in actions_repos:
        print(f"Scan de l'action : {repo_name}")
        report["scanned_actions"].append(repo_name)

        try:
            repo = g.get_repo(repo_name)
            
            # Récupération de l'arbre de fichiers complet (récursif)
            try:
                # On scanne la branche par défaut (souvent main ou master)
                # Note: Idéalement, il faudrait scanner le SHA spécifique utilisé, 
                # mais scanner la branche par défaut donne une bonne indication de l'état du projet.
                branch = repo.get_branch(repo.default_branch)
                tree = repo.get_git_tree(branch.commit.sha, recursive=True).tree
            except GithubException as e:
                print(f"Impossible de lire l'arbre de {repo_name}: {e}")
                continue

            # Filtrer les fichiers intéressants
            files_to_scan = [f for f in tree if f.path.endswith("package.json") or f.path.endswith("package-lock.json") or f.path.endswith("yarn.lock")]

            for file_obj in files_to_scan:
                try:
                    contents = repo.get_contents(file_obj.path)
                    decoded_content = contents.decoded_content.decode('utf-8')
                    found_packages = []

                    # Analyse package.json
                    if file_obj.path.endswith("package.json"):
                        try:
                            pkg_json = json.loads(decoded_content)
                            deps = {**pkg_json.get("dependencies", {}), **pkg_json.get("devDependencies", {})}
                            for pkg in target_packages:
                                if pkg in deps:
                                    found_packages.append({"package": pkg, "version": deps[pkg], "source": "package.json"})
                        except: pass

                    # Analyse package-lock.json (simplifiée texte pour rapidité ou json parsing)
                    elif file_obj.path.endswith("package-lock.json"):
                         # Recherche textuelle rapide pour éviter de parser des gros JSON si pas nécessaire
                         # Ou parsing complet si on veut être précis. Ici on fait simple :
                         for pkg in target_packages:
                             if f'"{pkg}"' in decoded_content:
                                 found_packages.append({"package": pkg, "version": "detected-in-lock", "source": "package-lock.json"})

                    # Analyse yarn.lock
                    elif file_obj.path.endswith("yarn.lock"):
                        for pkg in target_packages:
                            if f"{pkg}@" in decoded_content:
                                found_packages.append({"package": pkg, "version": "detected-in-lock", "source": "yarn.lock"})

                    if found_packages:
                        print(f"!!! ALERTE : Trouvé dans {repo_name} ({file_obj.path})")
                        report["matches"].append({
                            "repository": repo_name,
                            "file": file_obj.path,
                            "url": contents.html_url,
                            "found": found_packages
                        })

                except Exception as e:
                    print(f"Erreur lecture fichier {file_obj.path} sur {repo_name}: {e}")

        except GithubException as e:
            print(f"Erreur accès repo {repo_name}: {e}")
        except Exception as e:
            print(f"Erreur inattendue {repo_name}: {e}")

    # Sauvegarde du rapport
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)

    print(f"Scan terminé. Rapport : {REPORT_FILE}")

if __name__ == "__main__":
    scan_external_actions()
