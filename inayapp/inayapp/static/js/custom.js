(function ($) {
    "use strict";

    $(window).on('load', function () {
        $('#js-preloader').addClass('loaded');

        // Supprime complètement l'élément après l'animation
        setTimeout(function () {
            $("#js-preloader").remove();
        }, 1000);
    });

})(window.jQuery);


// Handle microphone permission
navigator.permissions.query({ name: 'microphone' }).then(function(permissionStatus) {
    if (permissionStatus.state === 'denied') {
        alert('Permission du microphone refusée. Veuillez l\'autoriser pour enregistrer l\'audio.');
        return;
    }
});

// Function to initialize audio recording
function initAudioRecording(recordButton, audioPlayback, audioDataInput, audioChunks) {
    let mediaRecorder;
    let stream;

    if (recordButton) {
        recordButton.addEventListener('click', async () => {
            if (!mediaRecorder || mediaRecorder.state === 'inactive') {
                try {
                    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);

                    mediaRecorder.start();
                    recordButton.textContent = '⏹️ Arrêter l\'enregistrement';

                    mediaRecorder.addEventListener('dataavailable', event => {
                        audioChunks.push(event.data);
                    });

                    mediaRecorder.addEventListener('stop', () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                        const audioUrl = URL.createObjectURL(audioBlob);
                        audioPlayback.src = audioUrl;
                        audioPlayback.style.display = 'block';

                        const reader = new FileReader();
                        reader.readAsDataURL(audioBlob);
                        reader.onloadend = function() {
                            audioDataInput.value = reader.result;
                        };

                        audioChunks.length = 0; // Clear audio chunks
                        stream.getTracks().forEach(track => track.stop());
                    });

                    recordButton.onclick = () => {
                        mediaRecorder.stop();
                        recordButton.textContent = '🎤 Enregistrer';
                    };
                } catch (err) {
                    alert('Erreur lors de l\'accès au microphone : ' + err.message);
                }
            }
        });
    }
}

// Initialize recording for each audio section
initAudioRecording(
    document.getElementById('recordAudio'),
    document.getElementById('audioPlayback'),
    document.getElementById('audioData'),
    []
);

initAudioRecording(
    document.getElementById('recordAudio1'),
    document.getElementById('audioPlayback1'),
    document.getElementById('audioData1'),
    []
);

initAudioRecording(
    document.getElementById('recordAudio2'),
    document.getElementById('audioPlayback2'),
    document.getElementById('audioData2'),
    []
);

initAudioRecording(
    document.getElementById('recordAudio3'),
    document.getElementById('audioPlayback3'),
    document.getElementById('audioData3'),
    []
);

// Function to validate file count
function validateFileCount(input) {
    const fileCount = input.files.length;

    if (fileCount > 10) {
        alert("Vous pouvez télécharger jusqu'à 10 fichiers maximum.");
        input.value = ""; // Reset file input
        return;
    }
}

