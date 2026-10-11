/*
 * The player that stays at the bottom, and the queue behind it.
 *
 * The queue lives in localStorage, so what you were listening to is still there
 * after browsing the library, and pressing play carries on where you stopped.
 *
 * Moving around does not stop the playback: internal links and forms are fetched
 * and swapped into this document (see `swap`), so the <audio> element is never
 * replaced and the browser - which only starts audio after a click - is never
 * asked to. Without JavaScript the app navigates as it always did; the playback
 * stops then, and one click on the bar carries on.
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

            const number = document.createElement("span");
            number.className = "queue-number";
            number.textContent = `${at + 1}.`;

            const title = document.createElement("span");
            title.className = "episode-title";
            title.textContent = item.title;

            const meta = document.createElement("span");
            meta.className = "episode-meta";
            // The queue's own count is the number above; this is the part.
            meta.textContent = item.part ? `${item.part}. díl` : "";

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

            line.append(number, title, meta, button);
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
                        part: Number(part.dataset.part) || null,
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
            return;
        }

        if (event.target.closest("#queue-clear")) {
            event.preventDefault();
            clearQueue();
            return;
        }

        followLink(event);
    });

    document.addEventListener("submit", (event) => {
        if (event.target instanceof HTMLFormElement) {
            followSubmit(event, event.target, event.submitter);
        }
    });

    window.addEventListener("popstate", () => {
        go(location.href, false);
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

    // --- moving inside the app without the playback noticing ------------------
    // A navigation loads a new document, and a new document means a new <audio>
    // element that a browser will not start without a click - which is how
    // opening the queue used to stop what you were listening to. Internal links
    // and forms are fetched and swapped into this document instead, so the
    // element playing stays where it is.

    let refreshTimer = 0;

    function isInternal(url) {
        return (
            url.origin === location.origin &&
            !url.pathname.startsWith("/library/") &&
            !url.pathname.startsWith("/static/")
        );
    }

    function refreshSeconds(document_) {
        const meta = document_.head.querySelector('meta[http-equiv="refresh"]');
        if (!meta) {
            return 0;
        }

        const match = /(\d+)/.exec(meta.getAttribute("content") || "");
        return match ? Number(match[1]) : 0;
    }

    function applyRefresh(seconds) {
        window.clearTimeout(refreshTimer);

        if (seconds > 0) {
            // A page that refreshes itself (a check or a download running) keeps
            // doing so - by swapping, not by loading everything again.
            refreshTimer = window.setTimeout(
                () => go(location.href, false),
                seconds * 1000
            );
        }
    }

    function swap(html) {
        const next = new DOMParser().parseFromString(html, "text/html");
        const keep = document.getElementById("player-bar");

        // Everything except the player bar and the scripts already running: the
        // bar holds the audio, and the script is this one.
        for (const node of Array.from(document.body.children)) {
            if (node !== keep && node.tagName !== "SCRIPT") {
                node.remove();
            }
        }

        // The new page's content takes its place, in order, above the bar.
        for (const node of Array.from(next.body.children)) {
            if (node.tagName === "SCRIPT" || node.id === "player-bar") {
                continue;
            }
            document.body.insertBefore(node, keep);
        }

        // The head is not swapped, so what the new page asked for is done here:
        // its title, and its wish to refresh.
        if (next.title) {
            document.title = next.title;
        }
        applyRefresh(refreshSeconds(next));
        window.scrollTo(0, 0);
        pageReady();
    }

    async function go(url, push = true) {
        try {
            const response = await fetch(url, { credentials: "same-origin" });
            const type = response.headers.get("content-type") || "";

            if (!response.ok || !type.includes("text/html")) {
                location.href = url;
                return;
            }

            swap(await response.text());

            if (push) {
                history.pushState({ swap: true }, "", response.url || url);
            }
        } catch (error) {
            // The network is the network: let the browser do it the old way.
            location.href = url;
        }
    }

    function followLink(event) {
        if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        ) {
            return;
        }

        const link = event.target.closest("a[href]");
        if (!link || link.target || link.hasAttribute("download")) {
            return;
        }

        const url = new URL(link.href, location.href);
        if (!isInternal(url)) {
            return;
        }

        if (url.pathname === location.pathname && url.search === location.search) {
            return; // a link to this very page: let it reload
        }

        event.preventDefault();
        go(url);
    }

    function followSubmit(event, form, submitter) {
        const url = new URL(form.getAttribute("action") || location.href, location.href);
        if (!isInternal(url)) {
            return;
        }

        // The fetch below stands in for the submission.
        event.preventDefault();
        const method = (form.getAttribute("method") || "get").toLowerCase();
        const data = new FormData(form);

        if (submitter && submitter.name) {
            data.append(submitter.name, submitter.value);
        }

        (async () => {
            try {
                const response = await fetch(url, {
                    method: method.toUpperCase(),
                    body: method === "post" ? data : undefined,
                    credentials: "same-origin",
                });
                const type = response.headers.get("content-type") || "";

                if (!response.ok || !type.includes("text/html")) {
                    form.submit();
                    return;
                }

                swap(await response.text());
                history.pushState({ swap: true }, "", response.url || url);
            } catch (error) {
                form.submit();
            }
        })();
    }

    // What every page needs once its markup is there - a swapped-in one included.
    function pageReady() {
        show();
        renderQueue();
    }

    // A page loaded whole may itself be asking to refresh (a check or a download
    // running); from here on that is done by swapping too, so the playback runs on.
    const loadRefresh = refreshSeconds(document);
    if (loadRefresh) {
        document
            .querySelectorAll('meta[http-equiv="refresh"]')
            .forEach((meta) => meta.remove());
        applyRefresh(loadRefresh);
    }

    pageReady();
})();
