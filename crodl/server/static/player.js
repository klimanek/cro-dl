/*
 * The player that stays at the bottom, and the queue behind it.
 *
 * The queue lives in localStorage, so what you were listening to is still there
 * after browsing the library, and pressing play carries on where you stopped.
 * Playback itself pauses when the page changes: a new document means a new
 * <audio> element, and a browser only lets a script start it after a click. So
 * the bar stays, the place is kept, and one click resumes.
 */
(() => {
    "use strict";

    const QUEUE_KEY = "crodl.queue";
    const STATE_KEY = "crodl.player";

    const bar = document.getElementById("player-bar");
    if (!bar) {
        return;
    }

    const audio = document.getElementById("player-audio");
    const title = document.getElementById("player-title");
    const work = document.getElementById("player-work");
    const counter = document.getElementById("player-count");
    const playButton = document.getElementById("player-play");
    const seek = document.getElementById("player-seek");

    let queue = read(QUEUE_KEY, []);
    let saved = read(STATE_KEY, {});
    let index = typeof saved.index === "number" ? saved.index : 0;
    let position = typeof saved.position === "number" ? saved.position : 0;
    let lastSaved = 0;

    // Tells the stylesheet that the play buttons mean something.
    document.documentElement.classList.add("js");

    function read(key, fallback) {
        try {
            const value = JSON.parse(localStorage.getItem(key));
            return value === null ? fallback : value;
        } catch (error) {
            return fallback;
        }
    }

    function save() {
        localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
        localStorage.setItem(
            STATE_KEY,
            JSON.stringify({ index, position: audio.currentTime || position })
        );

        // If this is the queue page, it mirrors what just changed (otherwise this
        // returns at once).
        renderQueue();
    }

    // The queue page (see /fronta): the same queue, as a list you can play from.
    function renderQueue() {
        const list = document.getElementById("queue-list");
        if (!list) {
            return;
        }

        const summary = document.getElementById("queue-summary");
        const empty = document.getElementById("queue-empty");
        list.textContent = "";

        if (summary) {
            summary.textContent = queue.length ? `${queue.length} položek` : "";
        }

        if (empty) {
            empty.hidden = queue.length > 0;
        }

        queue.forEach((item, at) => {
            const row = document.createElement("div");
            row.className =
                at === index ? "episode-item queue-item--current" : "episode-item";

            const line = document.createElement("div");
            line.className = "episode-row";

            const title = document.createElement("span");
            title.className = "episode-title";
            title.textContent = `${at + 1}. ${item.title}`;

            const work = document.createElement("span");
            work.className = "episode-meta";
            work.textContent = item.work || "";

            const button = document.createElement("button");
            button.type = "button";
            button.className = "play-button";
            button.textContent = at === index && !audio.paused ? "⏸" : "▶";
            button.title = "Přehrát tento díl";
            button.addEventListener("click", () => {
                if (at === index && !audio.paused) {
                    audio.pause();
                } else {
                    playAt(at, false);
                }
            });

            line.append(title, work, button);
            row.append(line);
            list.append(row);
        });
    }

    function clearQueue() {
        audio.pause();
        audio.removeAttribute("src");
        queue = [];
        index = 0;
        position = 0;
        save();
        show();
    }

    document.getElementById("player-clear").addEventListener("click", clearQueue);

    const clearAll = document.getElementById("queue-clear");
    if (clearAll) {
        clearAll.addEventListener("click", clearQueue);
    }

    function current() {
        return queue[index] || null;
    }

    function show() {
        const item = current();
        bar.hidden = !item;

        if (!item) {
            return;
        }

        title.textContent = item.title;
        work.textContent = item.work || "";
        counter.textContent = `${index + 1} / ${queue.length}`;

        if (audio.getAttribute("src") !== item.src) {
            audio.src = item.src;
            audio.currentTime = position;
        }
    }

    function playAt(target, resume) {
        if (!queue.length) {
            return;
        }

        index = Math.max(0, Math.min(target, queue.length - 1));

        if (!resume) {
            position = 0;
        }

        audio.src = queue[index].src;
        audio.currentTime = position;
        show();
        audio.play().catch(() => {}); // a browser may refuse without a click
        save();
    }

    function enqueue(items, start) {
        const known = new Set(queue.map((item) => item.src));
        const added = items.filter((item) => item.src && !known.has(item.src));
        const wasEmpty = queue.length === 0;

        queue = queue.concat(added);
        const first = added.length
            ? queue.indexOf(added[0])
            : queue.findIndex((item) => item.src === (items[0] || {}).src);

        if (start && first >= 0) {
            playAt(first, false);
        } else {
            if (wasEmpty && first >= 0) {
                index = first;
            }
            // The bar has to catch up even when nothing starts playing: the part
            // count moved, and that is what the queue is showing.
            show();
        }

        save();
    }

    document.addEventListener("click", (event) => {
        const part = event.target.closest("[data-play]");
        if (part) {
            event.preventDefault();
            enqueue(
                [
                    {
                        src: part.dataset.src,
                        title: part.dataset.title,
                        work: part.dataset.work,
                    },
                ],
                true
            );
            return;
        }

        const workButton = event.target.closest("[data-queue]");
        if (workButton) {
            event.preventDefault();
            fetch(workButton.dataset.queue)
                .then((response) => response.json())
                .then((data) => {
                    enqueue(data.items || [], false);
                    workButton.textContent = "✓ Ve frontě";
                })
                .catch(() => {});
        }
    });

    document.getElementById("player-prev").addEventListener("click", () => {
        playAt(index - 1, false);
    });

    document.getElementById("player-next").addEventListener("click", () => {
        playAt(index + 1, false);
    });

    document.getElementById("player-clear").addEventListener("click", () => {
        clearQueue();
    });

    playButton.addEventListener("click", () => {
        if (audio.paused) {
            audio.play().catch(() => {});
        } else {
            audio.pause();
        }
    });

    audio.addEventListener("play", () => {
        playButton.textContent = "⏸";
    });

    audio.addEventListener("pause", () => {
        playButton.textContent = "▶";
    });

    audio.addEventListener("ended", () => {
        if (index + 1 < queue.length) {
            playAt(index + 1, false);
        } else {
            position = 0;
            save();
        }
    });

    audio.addEventListener("timeupdate", () => {
        if (audio.duration) {
            seek.value = String(
                Math.round((audio.currentTime / audio.duration) * 100)
            );
        }

        const now = Date.now();
        if (now - lastSaved > 5000) {
            lastSaved = now;
            save();
        }
    });

    seek.addEventListener("input", () => {
        if (audio.duration) {
            audio.currentTime = (Number(seek.value) / 100) * audio.duration;
        }
    });

    window.addEventListener("pagehide", save);

    show();
    // The queue page draws itself on load, before anything is played.
    renderQueue();
})();
