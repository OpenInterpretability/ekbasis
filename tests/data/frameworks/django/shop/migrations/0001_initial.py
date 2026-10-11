from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel("Customer", [("id", models.AutoField(primary_key=True)),
                                            ("name", models.CharField(max_length=100)),
                                            ("email", models.CharField(max_length=200, null=True))]),
    ]
