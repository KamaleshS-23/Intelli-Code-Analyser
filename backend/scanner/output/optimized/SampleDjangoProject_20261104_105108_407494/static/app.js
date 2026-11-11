const savedCount = document.getElementById("saved-count");
const saveButtons = document.querySelectorAll(".save-book");
const savedBooks = new Set();

function updateSavedCount() {
  const count = savedBooks.size;
  savedCount.textContent = `${count} ${count === 1 ? "book" : "books"} saved`;
}

saveButtons.forEach((button) => {
  button.addEventListener("click", () => {
    savedBooks.add(button.dataset.book);
    updateSavedCount();
  });
});

updateSavedCount();
