from django.db import migrations


DEFAULT_CATEGORIES = (
    "Administrativo e Financeiro",
    "Instalações e Manutenção",
    "Recursos Humanos",
    "Suprimentos e Materiais",
    "Tecnologia e Informática",
)


def create_default_categories(apps, schema_editor):
    Category = apps.get_model("tickets", "Category")
    for name in DEFAULT_CATEGORIES:
        Category.objects.update_or_create(name=name, defaults={"active": True})


def remove_default_categories(apps, schema_editor):
    Category = apps.get_model("tickets", "Category")
    Category.objects.filter(name__in=DEFAULT_CATEGORIES, tickets__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("tickets", "0002_first_response_and_comment_updated")]
    operations = [
        migrations.RunPython(create_default_categories, remove_default_categories),
    ]
