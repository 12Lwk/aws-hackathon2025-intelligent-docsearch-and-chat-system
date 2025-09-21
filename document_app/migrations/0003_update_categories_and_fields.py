from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('document_app', '0002_document_classification_method_and_more'),
    ]

    operations = [
        # Update category choices
        migrations.AlterField(
            model_name='document',
            name='category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('policies_guidelines', 'Policies & Guidelines'),
                    ('operations_production', 'Operations & Production'),
                    ('maintenance_technical', 'Maintenance & Technical'),
                    ('training_knowledge', 'Training & Knowledge'),
                    ('others', 'Others')
                ],
                max_length=30
            ),
        ),
        # Remove old fields
        migrations.RemoveField(
            model_name='document',
            name='textract_success',
        ),
        migrations.RemoveField(
            model_name='document',
            name='comprehend_success',
        ),
        # Add new fields
        migrations.AddField(
            model_name='document',
            name='processed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='document',
            name='error_message',
            field=models.TextField(blank=True),
        ),
        # Update classification method help text
        migrations.AlterField(
            model_name='document',
            name='classification_method',
            field=models.CharField(
                blank=True,
                help_text='Method used for classification (bedrock, fallback, text)',
                max_length=50
            ),
        ),
    ]