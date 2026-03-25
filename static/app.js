const chatWindow = document.getElementById("chatWindow");
const chatForm = document.getElementById("chatForm");
const userInput = document.getElementById("userInput");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const nameInput = document.getElementById("nameInput");
const passwordInput = document.getElementById("passwordInput");
const registerName = document.getElementById("registerName");
const registerBalance = document.getElementById("registerBalance");
const registerType = document.getElementById("registerType");
const authStatus = document.getElementById("authStatus");
const logoutBtn = document.getElementById("logoutBtn");
const accountTypeLabel = document.getElementById("accountTypeLabel");

let loggedInUser = null;

function addBubble(text, who) {
  const node = document.createElement("div");
  node.className = `bubble ${who}`;
  node.textContent = text;
  chatWindow.appendChild(node);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

addBubble(
  "Please login with customer name and password",  
  "bot"
);

setChatEnabled(false);

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = registerName.value.trim();
  const balance = registerBalance.value.trim();
  const ac_type = registerType.value.trim();
  if (!name || !balance || !ac_type) return;

  try {
    const response = await fetch("/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, balance, ac_type }),
    });

    const data = await response.json();
    if (!response.ok) {
      addBubble(data.error || "Registration failed", "bot");
      return;
    }

    addBubble(
      `User created with id ${data.customer_id}. Use password ${data.default_password} to login.`,
      "bot"
    );

    nameInput.value = name;
    passwordInput.value = data.default_password;
    registerForm.reset();
  } catch (error) {
    addBubble("Server error during registration", "bot");
  }
});

function setChatEnabled(enabled) {
  userInput.disabled = !enabled;
  chatForm.querySelector("button").disabled = !enabled;
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = nameInput.value.trim();
  const password = passwordInput.value.trim();
  if (!name || !password) return;

  try {
    const response = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, password }),
    });

    const data = await response.json();
    if (!response.ok) {
      authStatus.textContent = data.error || "Login failed";
      addBubble(authStatus.textContent, "bot");
      return;
    }

    loggedInUser = data.user;
    const accountType = data.account_type || "Not available";
    authStatus.textContent = `Logged in as ${loggedInUser}`;
    accountTypeLabel.textContent = `Account type: ${accountType}`;
    logoutBtn.disabled = false;
    setChatEnabled(true);
    addBubble(`Welcome ${loggedInUser}. You can now chat.`, "bot");
    userInput.focus();
  } catch (error) {
    authStatus.textContent = "Server error during login";
    addBubble(authStatus.textContent, "bot");
  }
});

logoutBtn.addEventListener("click", async () => {
  try {
    await fetch("/logout", { method: "POST" });
  } catch (error) {
    // Ignore network errors and reset local state anyway.
  }

  loggedInUser = null;
  authStatus.textContent = "Not logged in";
  accountTypeLabel.textContent = "Account type: Not available";
  logoutBtn.disabled = true;
  setChatEnabled(false);
  addBubble("You are logged out.", "bot");
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!loggedInUser) {
    addBubble("Please login first.", "bot");
    return;
  }

  const message = userInput.value.trim();
  if (!message) return;

  addBubble(message, "user");
  userInput.value = "";
  userInput.focus();

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    const data = await response.json();
    if (!response.ok) {
      addBubble(data.error || "Something went wrong.", "bot");
      return;
    }

    addBubble(data.reply, "bot");
  } catch (error) {
    addBubble("Server error. Check if Flask is running.", "bot");
  }
});
