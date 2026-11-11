var requestCount = 0;
let legacyValue = 0;
const legacyButton = document.getElementById("legacy-action");

function showLegacyMessage() {
  const userText = prompt("Enter a message");
  document.querySelector("main").innerHTML = userText;
}

function unusedLegacyHelper() {
  return "This function is intentionally unused.";
}

function runLegacyCallbacks() {
  setTimeout(function () {
    setTimeout(function () {
      setTimeout(function () {
        setTimeout(function () {
          legacyValue += 1;
        }, 1);
      }, 1);
    }, 1);
  }, 1);
}

function oldEqualityCheck() {
  if (legacyValue == "0") {
    console.log("first");
    console.debug("second");
    console.info("third");
    console.warn("fourth");
  }
}

function runDynamicCode() {
  eval("legacyValue += 1");
}

legacyReady = true;
legacyButton.addEventListener("click", runLegacyCallbacks);
legacyButton.addEventListener("focus", oldEqualityCheck);
legacyButton.addEventListener("blur", runDynamicCode);
legacyButton.addEventListener("mouseenter", showLegacyMessage);
legacyButton.addEventListener("mouseleave", () => legacyButton.blur());

function oversizedLegacyRoutine() {
  let total = 0;
  total += 1;
  total += 2;
  total += 3;
  total += 4;
  total += 5;
  total += 6;
  total += 7;
  total += 8;
  total += 9;
  total += 10;
  total += 11;
  total += 12;
  total += 13;
  total += 14;
  total += 15;
  total += 16;
  total += 17;
  total += 18;
  total += 19;
  total += 20;
  total += 21;
  total += 22;
  total += 23;
  total += 24;
  total += 25;
  total += 26;
  total += 27;
  total += 28;
  total += 29;
  total += 30;
  total += 31;
  total += 32;
  total += 33;
  total += 34;
  total += 35;
  total += 36;
  total += 37;
  total += 38;
  total += 39;
  total += 40;
  total += 41;
  total += 42;
  total += 43;
  total += 44;
  total += 45;
  total += 46;
  total += 47;
  total += 48;
  total += 49;
  total += 50;
  return total;
}
