const portrait = document.getElementById("portrait");
let version = -1;
let currentImage = null;

function hopPortrait() {
    portrait.classList.remove("portrait-hop");
    void portrait.offsetWidth;
    portrait.classList.add("portrait-hop");
}

portrait.addEventListener("animationend", () => {
    portrait.classList.remove("portrait-hop");
});

async function refreshPortrait() {
    try {
        const response = await fetch("/api/state", { cache: "no-store" });
        if (!response.ok) return;

        const state = await response.json();
        if (state.version === version) return;

        version = state.version;
        if (state.image !== currentImage) {
            const shouldHop = currentImage !== null;
            currentImage = state.image;
            portrait.src = `/assets/${encodeURIComponent(state.image)}.png`;
            if (shouldHop) hopPortrait();
        }
    } catch (_) {
        // The next polling cycle retries when the local server is available.
    }
}

refreshPortrait();
setInterval(refreshPortrait, 250);
