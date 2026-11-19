# Le Quotidien Tech — collecte et livraison (gratuit, sans PC allumé)

Toutes les ~20 minutes, **GitHub Actions** lance `pipeline.py`, qui :

1. repère les nouveaux utilisateurs et les réglages modifiés (heure, jours, fuseau) et calcule la prochaine livraison ;
2. lit les flux RSS (au plus toutes les ~2 h) et regroupe les doublons ;
3. compose l'édition de chaque utilisateur dont l'heure approche (**jusqu'à 45 min avant**, pour absorber
   les retards éventuels de GitHub) et l'écrit dans Firestore ;
4. supprime chaque nuit les articles > 7 jours et les éditions > 60 jours.

Coût : 0 €. Dépôt **public** = minutes GitHub Actions gratuites ; Firebase reste sur le plan **Spark** (sans carte).
Aucune IA générative. Les journaux GitHub sont publics : le script n'y écrit aucun identifiant ni donnée personnelle.

## Mise en place (une seule fois)

### 1. Compte GitHub (gratuit, sans carte)
https://github.com/signup — le nom d'utilisateur sera visible dans l'adresse du dépôt : choisissez un pseudo si vous préférez.

### 2. Dépôt public
https://github.com/new → nom `quotidien-tech-pipeline` → **Public** → ne cochez **aucune** case
(ni README, ni .gitignore, ni licence) → *Create repository*.

### 3. Envoyer le code (terminal VS Code)
Décompressez `quotidien-pipeline.zip` dans `C:\dev\quotidien\` (vous obtenez `C:\dev\quotidien\quotidien-pipeline`).
Si l'e-mail de commit est public, GitHub l'affiche : utilisez l'adresse « noreply » indiquée sur
https://github.com/settings/emails (de la forme `123456+pseudo@users.noreply.github.com`).

```
cd C:\dev\quotidien\quotidien-pipeline
git config --global user.name "Votre pseudo"
git config --global user.email "123456+pseudo@users.noreply.github.com"
git init -b main
git add .
git status
```
`git status` doit lister des fichiers `.py`, `.json`, `.yml`… mais **aucune clé** (pas de `cle.json`). Puis :
```
git commit -m "Premier envoi"
git remote add origin https://github.com/VOTRE_PSEUDO/quotidien-tech-pipeline.git
git push -u origin main
```
Une fenêtre de navigateur s'ouvre pour vous connecter à GitHub : acceptez.

### 4. Le secret (clé d'accès à Firestore) — jamais sur votre PC, jamais dans le code
1. Console Firebase → ⚙ **Paramètres du projet** → **Comptes de service** → **Générer une nouvelle clé privée**.
2. Ouvrez le fichier téléchargé avec le Bloc-notes → `Ctrl+A`, `Ctrl+C`.
3. GitHub → votre dépôt → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
   - Name : `FIREBASE_SERVICE_ACCOUNT`
   - Secret : `Ctrl+V` → **Add secret**.
4. **Supprimez** le fichier téléchargé (dossier Téléchargements, puis corbeille).
5. Supprimez aussi l'ancienne clé : `C:\dev\secrets\cle.json`, et dans la console Google Cloud
   (IAM et administration → Comptes de service → compte `firebase-adminsdk…` → onglet **Clés**) la clé
   ancienne (laissez uniquement la nouvelle).

### 5. Premier lancement
Dépôt → onglet **Actions** → si GitHub le demande, cliquez « I understand my workflows, go ahead and enable them »
→ **Édition quotidienne** → **Run workflow**. Ouvrez l'exécution : une coche verte et, dans « Collecter, composer et
livrer », des lignes `collecte : N nouveaux … flux en erreur` puis `terminé`.

Un nouvel utilisateur reçoit **tout de suite une première édition** : elle apparaît dans l'appli sans rien faire.

## Après la mise en place

* **Changer l'heure** dans l'appli : prise en compte à la prochaine exécution (≤ 20 min, parfois plus).
* **Tester sans attendre demain** : réglez l'heure de livraison 10 à 30 minutes dans le futur, puis lancez
  « Run workflow » : l'édition est composée dans la fenêtre des 45 minutes.
* **Un flux en erreur** (`flux en erreur` > 0) : ce n'est pas bloquant, les autres sources suffisent. Regardez
  les lignes `WARNING` pour connaître la source, puis corrigez son adresse dans `quotidien/sources.py`.
* **Règle des 60 jours** : GitHub coupe les tâches planifiées d'un dépôt public sans activité. La dernière étape du
  workflow crée un petit commit vide si le dernier a plus de 45 jours. Si un jour plus rien ne se lance, onglet
  Actions → réactivez le workflow.
* **Retards GitHub** : l'exécution peut démarrer 5 à 30 min après l'heure prévue, voire être sautée lors d'un incident.
  L'édition est donc préparée avant l'heure choisie ; elle peut apparaître dans l'appli un peu avant 8 h.

## Tests locaux (hors ligne)
```
python -m unittest discover -s tests -t .
```

## Données (inchangé)
`users/{uid}` (écrit par l'appli) : `topics`, `timezone`, `deliveryTime`, `deliveryDays`, `deliveryCustomDays`,
`fcmTokens`, `audio`, `prefs`. Champs réservés au serveur : `nextDeliveryAt`, `scheduleSig`, `lastEditionDate`.
`users/{uid}/editions/{AAAA-MM-JJ}` : `une`, `more[]`, `brefs[]`, `articleIds`, `createdAt`.
`config/pipeline` : dates de dernière collecte / dernier nettoyage.
Le catalogue `quotidien/topics.json` doit rester identique à `assets/topics.json` de l'appli.

Règles Firestore : inchangées (déjà déployées). Pour les redéployer : `firebase deploy --only firestore`.
