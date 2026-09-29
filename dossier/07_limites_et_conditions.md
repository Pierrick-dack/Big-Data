# 07 — Limites et conditions d'usage

- **Fuseau horaire** : la conversion UTC→local est faite par +2 h, valable sur la fenêtre des
  données (été, CEST, sans changement d'heure). Hors été, activer un vrai fuseau `Europe/Paris`.
- **Manque à gagner** : estimé via un proxy (recherches « aucun engin » × panier moyen). C'est un
  ordre de grandeur pour prioriser, pas une comptabilité exacte : une partie des clients aurait renoncé.
- **Pseudonymisation** : md5 salé pour la reproductibilité de l'épreuve ; en production, HMAC-SHA256
  avec un secret conservé hors du dépôt.
- **Projection 2027** : hypothèse de ×5 engins et de relevé 2× plus fréquent ; à réviser selon le
  déploiement réel.
- **Corrélation météo** : indicative (association, non causalité).
