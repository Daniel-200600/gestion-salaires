"""Tests des modèles : construction correcte depuis une ligne sqlite3.Row."""

from database.connection import get_connection
from models.enseignant import Enseignant
from models.enums import Sexe, StatutEnseignant, StatutPeriode
from models.periode_paie import PeriodePaie


def test_enseignant_from_row(db_path):
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO enseignants (nom, prenom, sexe, statut, taux_horaire) "
            "VALUES ('Benali', 'Sara', 'F', 'V', 120.0)"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM enseignants").fetchone()

    enseignant = Enseignant.from_row(row)

    assert enseignant.nom == "Benali"
    assert enseignant.sexe == Sexe.FEMME
    assert enseignant.statut == StatutEnseignant.VACATAIRE
    assert enseignant.taux_horaire == 120.0
    assert enseignant.actif is True


def test_periode_paie_from_row(db_path):
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO periodes_paie (mois, annee, libelle) VALUES (10, 2026, 'Octobre 2026')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM periodes_paie").fetchone()

    periode = PeriodePaie.from_row(row)

    assert periode.mois == 10
    assert periode.annee == 2026
    assert periode.statut == StatutPeriode.BROUILLON
