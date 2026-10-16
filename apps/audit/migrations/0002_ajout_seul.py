"""D45 : un déclencheur PostgreSQL interdit tout UPDATE et tout DELETE sur le journal d'audit.

Même un accès direct à la base (psql, un script, une erreur de développeur) ne peut pas réécrire l'histoire.
Pas de déclencheur TRUNCATE : Django vide les tables entre deux tests avec TRUNCATE ; la disparition d'entrées
est de toute façon détectée par ``verifier_chaine`` (la tête de chaîne ne correspond plus).
"""
from django.db import migrations

CREER = """
CREATE FUNCTION audit_interdire_modification() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Le journal d''audit est en ajout seul : % interdit.', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_entreeaudit_ajout_seul
    BEFORE UPDATE OR DELETE ON audit_entreeaudit
    FOR EACH ROW EXECUTE FUNCTION audit_interdire_modification();
"""

SUPPRIMER = """
DROP TRIGGER IF EXISTS audit_entreeaudit_ajout_seul ON audit_entreeaudit;
DROP FUNCTION IF EXISTS audit_interdire_modification();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(CREER, reverse_sql=SUPPRIMER)]
