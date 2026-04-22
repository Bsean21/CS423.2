const reviewInput = document.getElementById("review-input");
const submitButton = document.getElementById("submit-review-btn");
const submitMessage = document.getElementById("submit-message");

submitButton.addEventListener("click", submitReview);

async function checkServerStatus() {
  return;
}

async function submitReview() {
  const review = reviewInput.value.trim();
  if (!review) {
    renderSubmitMessage("Please type a review before submitting.", false);
    return;
  }

  try {
    const response = await fetch("/api/reviews", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ review })
    });

    const data = await response.json();
    if (!response.ok) {
      renderSubmitMessage(data.error || "Failed to submit review.", false);
      return;
    }

    reviewInput.value = "";
    renderSubmitMessage("Review submitted successfully. The admin can now analyze it.", true);
  } catch (error) {
    renderSubmitMessage("Flask server is not reachable yet. Start app.py first.", false);
  }
}

function renderSubmitMessage(message, ok) {
  submitMessage.textContent = message;
  submitMessage.style.color = ok ? "#1b6b43" : "#a62828";
}

checkServerStatus();
