document.addEventListener("DOMContentLoaded", function () {
    const savedTheme = localStorage.getItem("interviewmate-theme");
    if (savedTheme === "light") document.body.classList.add("light-mode");
    const themeSelect = document.querySelector('select[name="theme"]');
    if (themeSelect) {
        themeSelect.addEventListener("change", function () {
            localStorage.setItem("interviewmate-theme", themeSelect.value);
            document.body.classList.toggle("light-mode", themeSelect.value === "light");
        });
    }

    const menuToggle = document.querySelector(".menu-toggle");
    const sidebar = document.querySelector(".sidebar");
    if (menuToggle && sidebar) {
        menuToggle.addEventListener("click", () => sidebar.classList.toggle("open"));
    }

    const canvas = document.querySelector("#progress-chart");
    if (canvas) {
        const ctx = canvas.getContext("2d");
        const labels = JSON.parse(canvas.dataset.labels || "[]");
        const values = JSON.parse(canvas.dataset.values || "[]");
        const width = canvas.clientWidth || 600;
        const height = 190;
        canvas.width = width * window.devicePixelRatio;
        canvas.height = height * window.devicePixelRatio;
        ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        ctx.clearRect(0, 0, width, height);
        ctx.font = "11px DM Sans, Arial";
        ctx.textAlign = "center";
        ctx.fillStyle = "#7d879e";
        ctx.strokeStyle = "rgba(148,163,184,.09)";
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = 18 + i * 34;
            ctx.beginPath(); ctx.moveTo(32, y); ctx.lineTo(width - 10, y); ctx.stroke();
        }
        if (!values.length) {
            ctx.fillText("Complete an interview to start seeing progress", width / 2, height / 2);
        } else {
            const chartW = width - 42;
            const chartH = 145;
            const step = chartW / Math.max(values.length - 1, 1);
            const points = values.map((value, i) => ({
                x: 32 + i * step,
                y: 160 - (Math.max(0, Math.min(100, value)) / 100) * chartH
            }));
            const gradient = ctx.createLinearGradient(0, 20, 0, height);
            gradient.addColorStop(0, "rgba(124,131,255,.28)");
            gradient.addColorStop(1, "rgba(124,131,255,0)");
            ctx.beginPath();
            ctx.moveTo(points[0].x, 160);
            points.forEach(p => ctx.lineTo(p.x, p.y));
            ctx.lineTo(points[points.length - 1].x, 160);
            ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();
            ctx.beginPath();
            points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
            ctx.strokeStyle = "#858fff"; ctx.lineWidth = 3; ctx.stroke();
            points.forEach((p, i) => {
                ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
                ctx.fillStyle = "#dfe3ff"; ctx.fill();
                ctx.fillStyle = "#7d879e";
                ctx.fillText(labels[i] || "", p.x, 180);
            });
        }
    }

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