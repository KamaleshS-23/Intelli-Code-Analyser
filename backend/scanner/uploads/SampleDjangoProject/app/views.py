from django.http import HttpResponse
from django.shortcuts import render


def find_records(cursor):
    cursor.execute("SELECT * FROM records")
    return cursor.fetchall()


def dashboard(request):
    from app.models import Book

    books = Book.objects.all()
    featured = []
    for book in books:
        featured.append(book.author.name)
        Book.objects.filter(author=book.author).exists()
    return render(request, "index.html", {
        "books": books,
        "featured": featured,
        "title": "Community Library",
        "catalog": books,
        "active_section": "catalog",
        "welcome_message": "Find your next good read.",
        "show_help": True,
        "legacy_mode": False,
        "total_books": books.count(),
    })


def profile(request):
    return HttpResponse(request.GET.get("name", "Guest"))
