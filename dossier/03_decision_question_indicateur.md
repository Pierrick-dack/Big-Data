# 03 — Décision / question / indicateur

| Destinataire | Décision | Question | Indicateur (table Gold) | Maille |
|---|---|---|---|---|
| Exploitation (matin) | Où rééquilibrer avant 8 h ? | Où la demande n'est-elle pas servie ? | Taux de non-service (`gold_non_service`) | station × jour × heure |
| Exploitation (matin) | Quels engins recharger ? | Quels engins sous le seuil au réveil ? | Flotte au réveil (`gold_flotte_synthese`) | engin × jour |
| Direction (contrat) | Renouveler / renégocier / changer ? | Le prestataire tient-il le délai ? | Respect du contrat (`gold_sla_mensuel`) | intervention → mois |
| Direction (contrat) | Facturer des pénalités ? | Combien d'interventions hors délai ? | Respect du contrat (`gold_sla_interventions`) | intervention |
| Responsable flotte | Retirer / réparer / garantie ? | Quels engins/lots peu fiables ? | Fiabilité (`gold_fiabilite_lot`) | engin → lot |
| Analyse (cause) | Agir sur l'offre ou attendre ? | La météo explique-t-elle le non-service ? | Météo × non-service (`gold_meteo_nonservice`) | ville × jour |

Chaque indicateur est défini en détail dans l'interface (page « Dictionnaire des indicateurs »).
