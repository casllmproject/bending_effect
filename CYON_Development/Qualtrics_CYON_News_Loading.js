Qualtrics.SurveyEngine.addOnload(function() {
    // --- 0. Setup ---
    // Hide the "Next" button. It will only be clicked on success.
    this.hideNextButton();
    var that = this;

    // --- NEW: Countdown Timer Logic ---
    var countdownIntervalId;
    var timeLeft = 60; // 60 seconds
    const timerElement = document.getElementById('countdown-timer');

    function startCountdown() {
        if (!timerElement) {
            console.log("Countdown timer element not found.");
            return; // Don't start if the HTML element isn't there
        }

        // Immediately set the starting time
        timerElement.innerHTML = " " + timeLeft + "s";
        timeLeft--;

        countdownIntervalId = setInterval(() => {
            if (timeLeft <= 0) {
                // When timer hits 0, show a persistent message
                timerElement.innerHTML = "Still working... Please wait.";
                clearInterval(countdownIntervalId); // Stop counting down
            } else {
                // While running, update time
                timerElement.innerHTML = " " + timeLeft + "s";
                timeLeft--;
            }
        }, 1000); // Update every 1 second
    }
    // --- END NEW ---

    // --- 1. GATHER ALL EMBEDDED DATA FIELDS ---
    const surveyData = {
        DEM1: "${e://Field/DEM1}",
        DEM2: "${e://Field/DEM2}",
        DEM3: "${e://Field/DEM3}",
        DEM4: "${e://Field/DEM4}",
        DEM5: "${e://Field/DEM5}",
        DEM7: "${e://Field/DEM7}",
        DEM8: "${e://Field/DEM8}",
        VOT2: "${e://Field/VOT2}",
        CCP1_1: "${e://Field/CCP1_1}"
    };

    console.log("Sending to API:", surveyData); // Debugging

    // --- 2. DEFINE THE API ENDPOINT ---
    const API_URL = "https://qualtrics-gpt-news-generator-0lv-1063879666685.us-central1.run.app";
    const RETRY_DELAY = 5000; // Wait 5 seconds between retries
    const TIMEOUT_DURATION = 20000; // 20 seconds per attempt

    // --- 3. DEFINE THE RECURSIVE API CALL FUNCTION ---
    // This function will call itself on failure, creating a retry loop.
    async function attemptApiCall() {
        console.log("Attempting API call...");
        
        // We need a new AbortController for each attempt
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
            console.error("Fetch request timed out.");
            controller.abort();
        }, TIMEOUT_DURATION);

        try {
            const response = await fetch(API_URL, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(surveyData),
                signal: controller.signal
            });

            // Clear the timeout as soon as we get a response
            clearTimeout(timeoutId);

            if (!response.ok) {
                // Got a server error (e.g., 500, 404)
                const errorData = await response.json().catch(() => ({})); // Try to parse error
                let errorMsg = errorData.message || `Server responded with status ${response.status}`;
                throw new Error(errorMsg);
            }

            const data = await response.json();
            console.log("API Response:", data); // Debugging

            // --- 4. VALIDATE AND SAVE THE RESPONSE ---
            if (data.headline && data.body) {
                // SUCCESS! Save data and move on.

                // --- NEW: Stop the countdown on success ---
                clearInterval(countdownIntervalId);
                if (timerElement) {
                    timerElement.innerHTML = "Success!";
                }
                // --- END NEW ---

                Qualtrics.SurveyEngine.setEmbeddedData("generatedHeadline", data.headline);
                Qualtrics.SurveyEngine.setEmbeddedData("generatedBody", data.body);
                Qualtrics.SurveyEngine.setEmbeddedData("apiResponse", JSON.stringify(data));
                
                console.log("Success! Moving to next page.");
                // --- 5. AUTOMATICALLY MOVE TO NEXT PAGE ---
                that.clickNextButton();
            } else {
                // API returned 200 OK but data was incomplete
                throw new Error("API returned an incomplete response.");
            }

        } catch (error) {
            // --- HANDLE ANY FAILURE (TIMEOUT, NETWORK, BAD RESPONSE) ---
            
            // Always clear the timeout, even if it didn't fire
            clearTimeout(timeoutId);

            let userErrorMessage;
            if (error.name === 'AbortError') {
                userErrorMessage = "The request timed out. Retrying...";
            } else {
                userErrorMessage = `An API error occurred: ${error.message}. Retrying...`;
            }
            
            console.error(userErrorMessage);
            
            // Set a temporary error message (optional, but good for UX)
            // This will be overwritten on the next attempt or on success
            Qualtrics.SurveyEngine.setEmbeddedData("generatedHeadline", "Error");
            Qualtrics.SurveyEngine.setEmbeddedData("generatedBody", userErrorMessage);

            // --- 6. RETRY LOGIC ---
            // Wait for the specified delay, then call this function again.
            setTimeout(attemptApiCall, RETRY_DELAY);
        }
    }

    // --- 7. START THE COUNTDOWN AND THE API CALL ---
    // The function will now handle all retries internally.
    startCountdown();
    attemptApiCall();
});
