"""D37 : ``TerminalTirage`` devient ``Terminal`` (types « tirage » et « scène »), sans perdre les terminaux existants."""
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("concours", "0001_initial"),
        ("prestations", "0002_terminaltirage"),
    ]

    operations = [
        migrations.RenameModel(old_name="TerminalTirage", new_name="Terminal"),
        migrations.AlterModelOptions(
            name="terminal",
            options={
                "ordering": ["session", "nom"],
                "verbose_name": "terminal",
                "verbose_name_plural": "terminaux",
            },
        ),
        migrations.AlterField(
            model_name="terminal",
            name="session",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT, related_name="terminaux", to="concours.session"
            ),
        ),
        migrations.AddField(
            model_name="terminal",
            name="type",
            field=models.CharField(
                choices=[("tirage", "Tablette de tirage"), ("scene", "Écran de scène")],
                default="tirage",
                max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name="terminal",
            constraint=models.CheckConstraint(
                condition=Q(type="tirage") | Q(prestation_appelee__isnull=True),
                name="terminal_appel_reserve_au_tirage",
            ),
        ),
    ]
