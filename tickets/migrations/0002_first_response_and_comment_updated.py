from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0001_initial")]
    operations = [
        migrations.AddField(model_name="ticket", name="first_response_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="comment", name="updated_at", field=models.DateTimeField(auto_now=True)),
    ]
