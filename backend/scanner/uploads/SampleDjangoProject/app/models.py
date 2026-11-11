from django.db import models


class Author(models.Model):
    name = models.CharField()
    is_active = models.BooleanField(null=True)

    def books(self):
        return Book.objects.filter(author=self)


class Book(models.Model):
    title = models.CharField()
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    summary = models.TextField()
