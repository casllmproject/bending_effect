Qualtrics.SurveyEngine.addOnReady(function() {
  // ====== CONFIG ======
  var waitTime = 40000; // 40 seconds (in milliseconds)
  // ====================

  var nextButton = jQuery("#NextButton");
  var buttonParent = nextButton.parent();

  // 1. Initial Hiding of the Next button
  nextButton.hide();

  // 2. Hide Qualtrics Timing Metrics (original logic)
  jQuery(".Skin .QuestionOuter .QuestionBody .SkinInner table td").hide();
  jQuery(".QuestionBody table, .QuestionBody span:contains('Seconds')").hide();

  // 3. Create countdown display (original logic)
  var countdown = Math.ceil(waitTime / 1000);
  var timerDisplay = jQuery("<div>", {
    id: "timerDisplay",
    text: "Please wait " + countdown + " seconds...",
    css: {
      "font-size": "16px",
      "margin-top": "10px",
      "font-weight": "normal"
    }
  });
  buttonParent.append(timerDisplay);

  // 4. Set up the MutationObserver to enforce button hiding
  //    This is the key fix for Qualtrics automatically showing the button.
  var observer = new MutationObserver(function(mutationsList, observer) {
    // Check if the button is visible and the waitTime has not passed
    if (nextButton.is(':visible') && (Date.now() - startTime < waitTime)) {
      // If it's visible prematurely, hide it again immediately
      nextButton.hide();
      console.log("Observer caught and hid the Next Button."); // Optional: for debugging
    }
  });

  // Start observing the next button for style changes (which would reveal it)
  // The attributeFilter ensures it only triggers when the 'style' attribute changes.
  observer.observe(nextButton[0], { attributes: true, attributeFilter: ['style'] });
  
  // Record the start time for the observer check
  var startTime = Date.now();

  // 5. Update countdown every second (original logic)
  var timerInterval = setInterval(function() {
    countdown--;
    if (countdown > 0) {
      jQuery("#timerDisplay").text("Please wait " + countdown + " seconds...");
    } else {
      clearInterval(timerInterval);
      // We don't show the button here, just update the text, as setTimeout handles the showing
      jQuery("#timerDisplay").text("Done with reading? You may proceed."); 
    }
  }, 1000);

  // 6. Show Next button after waitTime
  setTimeout(function() {
    // Stop the observer so it doesn't hide the button when we show it
    observer.disconnect();
    
    // Now safely show the button
    nextButton.show();
    jQuery("#timerDisplay").text("Done with reading? You may proceed.");
    
  }, waitTime);
});
