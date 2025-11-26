import os
import csv
import json
from github import Github, GithubException

# Configuration
GITHUB_TOKEN = "TON GITHUB TOKEN"
CSV_FILE = "list.csv"
REPORT_FILE = "scan_report.json"

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

def scan_repositories():
    if not GITHUB_TOKEN:
        print("Erreur: Token GitHub manquant. Définissez la variable d'environnement GITHUB_TOKEN.")
        return

    g = Github(GITHUB_TOKEN)
    target_packages = load_target_packages(CSV_FILE)
    
    if not target_packages:
        print("Aucun package à rechercher.")
        return

    print(f"Recherche des packages : {target_packages}")
    
    report = {
        "scanned_repos": [],
        "matches": []
    }

    user = g.get_user()
    # Get all repos the user has access to
    repos = user.get_repos()

    print("Début du scan...")

    for repo in repos:
        repo_name = repo.full_name
        print(f"Scan de : {repo_name}")
        
        repo_info = {
            "name": repo_name,
            "package_files": [],
            "actions": []
        }
        report["scanned_repos"].append(repo_info)

        try:
            # Récupération de l'arbre de fichiers complet (récursif)
            try:
                branch = repo.get_branch(repo.default_branch)
                tree = repo.get_git_tree(branch.commit.sha, recursive=True).tree
            except GithubException as e:
                if e.status == 409: # Git Repository is empty
                     print(f"Repo vide : {repo_name}")
                     continue
                else:
                    raise e

            # Filtrer pour ne garder que les fichiers package.json, lockfiles et workflows
            package_files = [f for f in tree if f.path.endswith("package.json")]
            lock_files = [f for f in tree if f.path.endswith("package-lock.json") or f.path.endswith("yarn.lock")]
            workflow_files = [f for f in tree if f.path.startswith(".github/workflows/") and (f.path.endswith(".yml") or f.path.endswith(".yaml"))]
            
            # Enregistrement des fichiers trouvés
            repo_info["package_files"] = [f.path for f in package_files + lock_files]

            # Analyse des workflows pour trouver les 'uses'
            for wf_file in workflow_files:
                try:
                    contents = repo.get_contents(wf_file.path)
                    decoded_content = contents.decoded_content.decode('utf-8')
                    for line in decoded_content.splitlines():
                        if "uses:" in line:
                            # Extraction simple de l'action
                            parts = line.split("uses:")
                            if len(parts) > 1:
                                action = parts[1].strip().split("#")[0].strip()
                                # Nettoyage des quotes éventuelles
                                action = action.strip("'").strip('"')
                                repo_info["actions"].append({
                                    "file": wf_file.path,
                                    "action": action
                                })
                except Exception as e:
                    print(f"Erreur lors de l'analyse du workflow {wf_file.path} sur {repo_name}: {e}")

            # Analyse des fichiers de lock (package-lock.json et yarn.lock)
            for lock_file in lock_files:
                try:
                    contents = repo.get_contents(lock_file.path)
                    decoded_content = contents.decoded_content.decode('utf-8')
                    found_packages = []

                    if lock_file.path.endswith("package-lock.json"):
                        try:
                            json_content = json.loads(decoded_content)
                            all_lock_deps = {}
                            
                            # v1 dependencies
                            def extract_deps_v1(deps_dict):
                                for name, info in deps_dict.items():
                                    all_lock_deps[name] = info.get("version", "unknown")
                                    if "dependencies" in info:
                                        extract_deps_v1(info["dependencies"])
                            if "dependencies" in json_content:
                                extract_deps_v1(json_content["dependencies"])

                            # v2/v3 packages
                            if "packages" in json_content:
                                for key, info in json_content["packages"].items():
                                    name = key.split("node_modules/")[-1]
                                    if name:
                                        all_lock_deps[name] = info.get("version", "unknown")

                            for pkg in target_packages:
                                if pkg in all_lock_deps:
                                    found_packages.append({
                                        "package": pkg,
                                        "version": all_lock_deps[pkg],
                                        "source": "package-lock.json"
                                    })
                        except json.JSONDecodeError:
                            print(f"Erreur JSON dans {lock_file.path}")

                    elif lock_file.path.endswith("yarn.lock"):
                        # Analyse simplifiée pour yarn.lock
                        found_set = set()
                        for line in decoded_content.splitlines():
                            line = line.strip()
                            if not line or line.startswith("#"): continue
                            for pkg in target_packages:
                                # Détection basique : début de ligne avec "pkg@" ou pkg@
                                if line.startswith(f"{pkg}@") or line.startswith(f'"{pkg}@'):
                                    if pkg not in found_set:
                                        found_packages.append({
                                            "package": pkg,
                                            "version": "yarn-lock-detected",
                                            "source": "yarn.lock"
                                        })
                                        found_set.add(pkg)

                    if found_packages:
                        report["matches"].append({
                            "repository": repo_name,
                            "file": lock_file.path,
                            "url": contents.html_url,
                            "found": found_packages
                        })

                except Exception as e:
                    print(f"Erreur lors de l'analyse du lockfile {lock_file.path} sur {repo_name}: {e}")

            for pkg_file in package_files:
                try:
                    # Récupération du contenu du fichier
                    contents = repo.get_contents(pkg_file.path)
                    package_json = json.loads(contents.decoded_content.decode('utf-8'))
                    
                    dependencies = package_json.get("dependencies", {})
                    dev_dependencies = package_json.get("devDependencies", {})
                    all_deps = {**dependencies, **dev_dependencies}

                    found_packages = []
                    for pkg in target_packages:
                        if pkg in all_deps:
                            found_packages.append({
                                "package": pkg,
                                "version": all_deps[pkg]
                            })

                    if found_packages:
                        report["matches"].append({
                            "repository": repo_name,
                            "file": pkg_file.path,
                            "url": contents.html_url,
                            "found": found_packages
                        })
                except Exception as e:
                    print(f"Erreur lors de l'analyse de {pkg_file.path} sur {repo_name}: {e}")

        except GithubException as e:
            print(f"Erreur GitHub sur {repo_name}: {e}")
        except Exception as e:
            print(f"Erreur inattendue sur {repo_name}: {e}")

    # Sauvegarde du rapport
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)
    
    with open("repos_scanned.txt", 'w', encoding='utf-8') as f:
        for pkg in target_packages:
            f.write(f"{pkg}\n")

    print(f"Scan terminé. Rapport généré dans {REPORT_FILE}")

if __name__ == "__main__":
    scan_repositories()
