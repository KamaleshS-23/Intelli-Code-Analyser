from django.db import migrations, models


def populate_metadata(apps, schema_editor):
    Book = apps.get_model("app", "Book")
    Book.objects.all().update(summary="Imported legacy book")


class Migration(migrations.Migration):
    atomic = False
    operations = [
        migrations.AddField(
            model_name="book",
            name="edition",
            field=models.CharField(max_length=40, default="first"),
        ),
        migrations.RunPython(populate_metadata),
    ]
