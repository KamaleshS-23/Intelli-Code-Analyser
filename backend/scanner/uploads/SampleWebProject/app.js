// TODO: Replace local sample state with a persistent task service.
const form = document.querySelector("#task-form");
const input = document.getElementById("task-input");
const taskList = document.querySelector("#task-list");
const taskCount = document.getElementById("task-count");

function updateTaskCount() {
  const total = taskList.querySelectorAll("li").length;
  taskCount.textContent = `${total} ${total === 1 ? "task" : "tasks"}`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const title = input.value.trim();
  if (!title) return;

  const item = document.createElement("li");
  const label = document.createElement("span");
  const button = document.createElement("button");
  label.textContent = title;
  button.type = "button";
  button.className = "complete-task";
  button.textContent = "Complete";
  item.append(label, button);
  taskList.append(item);
  input.value = "";
  updateTaskCount();
});

taskList.addEventListener("click", (event) => {
  if (!event.target.matches(".complete-task")) return;
  event.target.closest("li").remove();
  updateTaskCount();
});

updateTaskCount();
