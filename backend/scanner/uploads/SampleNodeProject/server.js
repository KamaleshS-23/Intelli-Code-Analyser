const express = require("express");
const fs = require("fs");
const { exec } = require("child_process");
const jwt = require("jsonwebtoken");
const app = express();

app.use(express.json());

app.get("/api/books", async (req, res) => {
  const owner = req.query.owner;
  const books = await Book.find();
  res.json(books);
});

app.post("/api/books", async (req, res) => {
  const book = await Book.create(req.body);
  res.status(201).json(book);
});

app.get("/api/export", (req, res) => {
  exec(`cat ${req.query.file}`, (error, stdout) => {
    if (error) return res.status(500).send("Export failed");
    res.send(stdout);
  });
});

function issueToken(user) {
  return jwt.sign({ id: user.id }, "tiny-key");
}

const content = fs.readFileSync("data.txt", "utf8");
console.log(content);
eval("console.log('dynamic code')");
