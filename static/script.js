document.addEventListener("DOMContentLoaded", function () {
    const answerField = document.querySelector("#answer");
    const wordCount = document.querySelector("#word-count");
    if (answerField && wordCount) {
        function updateWordCount() {
            const words = answerField.value.trim().match(/\S+/g) || [];
            wordCount.textContent = `${words.length} ${words.length === 1 ? "word" : "words"}`;

            const text = answerField.value.toLowerCase();
            const detailCheck = document.querySelector("#check-detail");
            const structureCheck = document.querySelector("#check-structure");
            const exampleCheck = document.querySelector("#check-example");

            if (detailCheck) {
                detailCheck.dataset.state = words.length >= 25 ? "ready" : "pending";
            }
            if (structureCheck) {
                const hasStructure = /first|then|next|finally|however|because|therefore/.test(text);
                structureCheck.dataset.state = hasStructure ? "ready" : "pending";
            }
            if (exampleCheck) {
                const hasExample = /for example|for instance|in my|when i|i used|we used|project|as a result/.test(text);
                exampleCheck.dataset.state = hasExample ? "ready" : "pending";
            }
        }

        answerField.addEventListener("input", updateWordCount);
        updateWordCount();
    }

    const speakButton = document.querySelector("#speak-question");
    const voiceStatus = document.querySelector("#voice-status");
    const audioPlayer = document.querySelector("#question-audio");
    if (!speakButton || !voiceStatus || !audioPlayer) {
        return;
    }

    let audioUrl;
    speakButton.addEventListener("click", async function () {
        speakButton.disabled = true;
        voiceStatus.textContent = "Preparing your question...";

        try {
            const response = await fetch(speakButton.dataset.audioUrl, {
                method: "POST",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || "Could not generate question audio.");
            }

            const audioBlob = await response.blob();
            if (audioUrl) {
                URL.revokeObjectURL(audioUrl);
            }
            audioUrl = URL.createObjectURL(audioBlob);
            audioPlayer.src = audioUrl;
            audioPlayer.hidden = false;
            audioPlayer.load();

            try {
                await audioPlayer.play();
                voiceStatus.textContent = "Playing your question...";
            } catch {
                voiceStatus.textContent = "Audio is ready. Press play to hear the question.";
            }
        } catch (error) {
            voiceStatus.textContent = error.message || "Could not generate question audio.";
        } finally {
            speakButton.disabled = false;
        }
    });

    audioPlayer.addEventListener("ended", function () {
        voiceStatus.textContent = "Question audio finished.";
    });
});