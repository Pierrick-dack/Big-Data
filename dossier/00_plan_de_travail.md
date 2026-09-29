# 00 — Plan de travail

Projet : chaîne décisionnelle pour un opérateur de mobilité partagée (phase pilote,
4 villes). Objectif : mesurer la demande non servie et le respect du contrat de
recharge, et préparer le bulletin d'exploitation du matin.

## Démarche (Partie 1)
1. Cartographier les sources (format, volume, qualité, sensibilité, criticité).
2. Concevoir l'architecture en couches et la justifier (délai du bulletin, volume, cible 2027).
3. Construire l'ETL : ingestion tracée, normalisation, déduplication, intégrité.
4. Définir des règles de qualité (bloquantes / informatives), quarantaine, taux de rejet.
5. Traiter les données personnelles (pseudonymisation, minimisation).
6. Construire les tables d'indicateurs (maille + définition).
7. Réaliser l'interface d'analyse.
8. Rédiger les constats et la décision par destinataire.

## Jalons de vérification
- Le pipeline se régénère depuis les données par deux commandes.
- L'interface lit uniquement les couches produites.
- Chaque choix technique est justifié et ses limites documentées.

Historique traité : 2026-07-20 → 2026-09-13 (56 jours).
