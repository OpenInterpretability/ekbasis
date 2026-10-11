from django.db import migrations


def fill(apps, schema_editor):
    apps.get_model("shop", "Customer").objects.filter(name="").update(name="unknown")


class Migration(migrations.Migration):
    dependencies = [("shop", "0002_remove_email")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
