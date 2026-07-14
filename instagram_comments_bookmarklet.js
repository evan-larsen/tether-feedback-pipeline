/*
Instagram comments scraper bookmarklet source.

How to use:
1. Open an Instagram profile grid, post, or reel page in your browser.
2. Create a bookmark.
3. Paste the minified bookmarklet from `instagram_comments_bookmarklet.txt`
   into the bookmark URL/location field.
4. Click the bookmark while you are on Instagram.

What it does:
- On a single post/reel: expands comments and scrapes the current item
- On a profile/grid page: opens each loaded post/reel overlay, scrapes it,
  saves the CSV, closes the overlay, and continues
- Sends the CSV to a local helper server over WebSocket when available
- Falls back to downloading `instagram-comments-<id>.csv` in single-post mode

Notes:
- Batch mode works best from a profile grid where clicking a tile opens an overlay.
- Run `python save_instagram_comments_server.py` if you want files saved directly
  into the local `comments/` folder.
*/

(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const now = new Date();
  const cutoff = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  const selfUsername = "evan.builds.tether";
  const overlayWaitMs = 15000;
  const batchLoadRounds = 8;
  const batchLoadPauseMs = 1200;
  const debugPrefix = "[insta-bookmarklet]";
  const localSaverUrls = ["ws://localhost:8765"];

  const seenClicks = new WeakSet();

  const buttonText = (el) =>
    (el?.innerText || el?.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();

  const isVisible = (el) => {
    if (!el) {
      return false;
    }

    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.visibility !== "hidden" &&
      style.display !== "none"
    );
  };

  const scopeRoot = () => document.querySelector('div[role="dialog"]') || document;
  const overlayDialog = () => document.querySelector('div[role="dialog"]');
  const log = (...args) => console.log(debugPrefix, ...args);
  const describePost = (href, index, total) => {
    const label = href ? href.split("/").filter(Boolean).slice(-1)[0] : "unknown";
    if (typeof index === "number" && typeof total === "number") {
      return `post ${index + 1}/${total} (${label})`;
    }
    return `post ${label}`;
  };

  const isLoadMoreButton = (el) => {
    const text = buttonText(el);
    return /more comments|view all.*comments|load more comments|view replies|more replies|load more replies/.test(
      text
    );
  };

  const clickExpandableButtons = () => {
    let clicks = 0;
    const nodes = Array.from(
      scopeRoot().querySelectorAll('button, div[role="button"], span[role="button"]')
    );

    for (const node of nodes) {
      if (seenClicks.has(node) || !isLoadMoreButton(node) || !isVisible(node)) {
        continue;
      }

      seenClicks.add(node);
      node.click();
      clicks += 1;
    }

    return clicks;
  };

  const hasVisibleExpandableButtons = () =>
    Array.from(
      scopeRoot().querySelectorAll('button, div[role="button"], span[role="button"]')
    ).some((node) => isLoadMoreButton(node) && isVisible(node));

  const getScrollableCandidates = () =>
    Array.from(scopeRoot().querySelectorAll("div, section")).filter(
      (el) => el.scrollHeight > el.clientHeight + 80 && el.clientHeight > 150
    );

  const pickScrollTarget = () => {
    const dialog = document.querySelector('div[role="dialog"]');
    if (dialog) {
      const dialogCandidates = Array.from(dialog.querySelectorAll("div, section")).filter(
        (el) => el.scrollHeight > el.clientHeight + 80 && el.clientHeight > 150
      );

      if (dialogCandidates.length) {
        return dialogCandidates.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
      }
    }

    const candidates = getScrollableCandidates();
    return candidates.sort((a, b) => b.scrollHeight - a.scrollHeight)[0] || document.scrollingElement;
  };

  const currentPostId = () => {
    const match = location.pathname.match(/\/(reel|p)\/([^/]+)/);
    return match ? match[2] : "";
  };

  const normalizePostHref = (href) => {
    if (!href) {
      return "";
    }

    const url = new URL(href, location.origin);
    return `${url.origin}${url.pathname}`;
  };

  const findCommentButtons = () =>
    Array.from(
      scopeRoot().querySelectorAll('button, a, div[role="button"], span[role="button"]')
    ).filter((node) => {
      const text = buttonText(node);
      const aria = (node.getAttribute("aria-label") || "").toLowerCase();
      return (
        isVisible(node) &&
        (/comment/.test(text) || /comment/.test(aria)) &&
        !isLoadMoreButton(node)
      );
    });

  const ensureCommentsVisible = async () => {
    if (extractComments().length) {
      log("comments already visible");
      return;
    }

    const buttons = findCommentButtons();
    log("looking for comment buttons", buttons.length);
    for (const button of buttons) {
      log("opening comments panel");
      button.click();
      await sleep(800);
      if (extractComments().length || hasVisibleExpandableButtons()) {
        log("comments panel opened");
        return;
      }
    }

    log("no comment button opened anything");
  };

  const extractComments = () => {
    const root = scopeRoot();
    const items = Array.from(root.querySelectorAll("ul li"));
    const comments = [];
    const seen = new Set();

    const parseTimestampFromElement = (li) => {
      const timeEl = li.querySelector("time");
      if (!timeEl) {
        return null;
      }

      const datetimeValue = timeEl.getAttribute("datetime");
      if (datetimeValue) {
        const candidate = new Date(datetimeValue);
        if (!Number.isNaN(candidate.getTime())) {
          return candidate;
        }
      }

      const titleValue = timeEl.getAttribute("title");
      if (titleValue) {
        const candidate = new Date(titleValue);
        if (!Number.isNaN(candidate.getTime())) {
          return candidate;
        }
      }

      const textValue = (timeEl.innerText || timeEl.textContent || "").trim();
      if (textValue) {
        const candidate = new Date(textValue);
        if (!Number.isNaN(candidate.getTime())) {
          return candidate;
        }
      }

      return null;
    };

    const parseTimestampFromLines = (lines) => {
      for (let index = lines.length - 1; index >= 1; index -= 1) {
        const line = lines[index].trim();
        const normalized = line.toLowerCase();

        let match = normalized.match(/^(\d+)\s*([smhdw])$/);
        if (match) {
          const value = Number(match[1]);
          const unit = match[2];
          const multipliers = {
            s: 1000,
            m: 60 * 1000,
            h: 60 * 60 * 1000,
            d: 24 * 60 * 60 * 1000,
            w: 7 * 24 * 60 * 60 * 1000,
          };

          return new Date(now.getTime() - value * multipliers[unit]);
        }

        match = normalized.match(/^(\d+)\s*(minute|minutes|hour|hours|day|days|week|weeks)$/);
        if (match) {
          const value = Number(match[1]);
          const unit = match[2];
          const multipliers = {
            minute: 60 * 1000,
            minutes: 60 * 1000,
            hour: 60 * 60 * 1000,
            hours: 60 * 60 * 1000,
            day: 24 * 60 * 60 * 1000,
            days: 24 * 60 * 60 * 1000,
            week: 7 * 24 * 60 * 60 * 1000,
            weeks: 7 * 24 * 60 * 60 * 1000,
          };

          return new Date(now.getTime() - value * multipliers[unit]);
        }

        match = line.match(/^([A-Z][a-z]{2})\s+(\d{1,2})$/);
        if (match) {
          const candidate = new Date(`${match[1]} ${match[2]}, ${now.getFullYear()}`);
          if (!Number.isNaN(candidate.getTime())) {
            if (candidate > now) {
              candidate.setFullYear(candidate.getFullYear() - 1);
            }
            return candidate;
          }
        }

        match = line.match(/^([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})$/);
        if (match) {
          const candidate = new Date(`${match[1]} ${match[2]}, ${match[3]}`);
          if (!Number.isNaN(candidate.getTime())) {
            return candidate;
          }
        }
      }

      return null;
    };

    for (const li of items) {
      const usernameLink = li.querySelector('a[href^="/"]');
      if (!usernameLink) {
        continue;
      }

      const rawText = (li.innerText || "").trim();
      if (!rawText) {
        continue;
      }

      const lines = rawText
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);

      if (lines.length < 2) {
        continue;
      }

      const username = lines[0].replace(/^@/, "").trim();
      if (username.toLowerCase() === selfUsername) {
        continue;
      }

      const timestamp = parseTimestampFromElement(li) || parseTimestampFromLines(lines);
      if (!timestamp || timestamp < cutoff) {
        continue;
      }

      const filtered = lines.slice(1).filter((line) => {
        const normalized = line.toLowerCase();
        if (
          /^(like|reply|share|follow|following|edited)$/i.test(line) ||
          /^\d+[smhdwy]$/.test(normalized) ||
          /^\d+\s*(minute|minutes|hour|hours|day|days|week|weeks)$/i.test(line) ||
          /^[A-Z][a-z]{2}\s+\d{1,2}(,\s*\d{4})?$/.test(line) ||
          /^\d+\s*(like|likes|reply|replies)$/i.test(line) ||
          /^view replies$/i.test(line) ||
          /^hide replies$/i.test(line)
        ) {
          return false;
        }

        return true;
      });

      if (!filtered.length) {
        continue;
      }

      const comment = filtered[0];
      const extraLines = filtered.slice(1);
      const key = `${username}\n${comment}\n${timestamp.toISOString().slice(0, 10)}`;
      if (seen.has(key)) {
        continue;
      }

      seen.add(key);
      comments.push({
        username,
        comment,
        commentFull: filtered.join(" | "),
        extraLines,
        timestamp: timestamp.toISOString().slice(0, 10),
      });
    }

    return comments;
  };

  const saveViaLocalServer = async (postId, csv) => {
    const errors = [];

    for (const url of localSaverUrls) {
      try {
        log("connecting to local saver", url, postId);
        const result = await new Promise((resolve, reject) => {
          let settled = false;
          let socket;
          let timer;

          const finish = (fn, value) => {
            if (settled) {
              return;
            }
            settled = true;
            if (timer) {
              clearTimeout(timer);
            }
            if (
              socket &&
              (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
            ) {
              socket.close();
            }
            fn(value);
          };

          try {
            socket = new WebSocket(url);
          } catch (error) {
            reject(error);
            return;
          }

          timer = setTimeout(() => {
            finish(reject, new Error(`Timed out connecting to ${url}`));
          }, 6000);

          socket.onopen = () => {
            socket.send(
              JSON.stringify({
                post_id: postId,
                csv,
              })
            );
          };

          socket.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data);
              if (!data.ok) {
                finish(reject, new Error(data.error || `Unknown local save error via ${url}`));
                return;
              }

              finish(resolve, data);
            } catch (error) {
              finish(reject, error);
            }
          };

          socket.onerror = () => {
            finish(reject, new Error(`WebSocket connection failed for ${url}`));
          };
        });

        log("saved through local server", url, result.filename);
        return result;
      } catch (error) {
        log("local saver connection failed", url, error.message);
        errors.push(`${url}: ${error.message}`);
      }
    }

    throw new Error(`Local saver connection failed. ${errors.join(" | ")}`);
  };

  const downloadCsv = (postId, csv) => {
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `instagram-comments-${postId}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const buildCsv = (postId, comments) => {
    const csvEscape = (value) => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const rows = [
      ["post_id", "timestamp", "username", "comment", "comment_full", "extra_lines_count"],
      ...comments.map((item) => [
        postId,
        item.timestamp,
        item.username,
        item.comment,
        item.commentFull,
        item.extraLines.length,
      ]),
    ];
    return rows.map((row) => row.map(csvEscape).join(",")).join("\n");
  };

  const expandCurrentComments = async () => {
    if (hasVisibleExpandableButtons()) {
      log("loading all comments and replies");
      let lastCount = 0;
      let stagnantRounds = 0;

      for (let round = 0; round < 25; round += 1) {
        log(`expand round ${round + 1}`);
        clickExpandableButtons();

        const scrollTarget = pickScrollTarget();
        if (scrollTarget) {
          scrollTarget.scrollTop = scrollTarget.scrollHeight;
        }
        window.scrollTo(0, document.body.scrollHeight);

        await sleep(1200);

        clickExpandableButtons();
        await sleep(600);

        const currentCount = extractComments().length;
        log("current extracted comments", currentCount);
        if (currentCount <= lastCount) {
          stagnantRounds += 1;
        } else {
          stagnantRounds = 0;
          lastCount = currentCount;
        }

        if (stagnantRounds >= 4 || !hasVisibleExpandableButtons()) {
          log("finished expanding comments");
          break;
        }
      }
    } else {
      log("no expandable comments UI found");
    }
  };

  const scrapeCurrentPost = async ({ batchMode = false } = {}) => {
    const postId = currentPostId();
    if (!postId) {
      throw new Error("No Instagram post/reel is currently open.");
    }

    log("scraping current post", postId);
    await ensureCommentsVisible();
    await expandCurrentComments();

    const comments = extractComments();
    log("comment extraction complete", postId, comments.length);
    if (!comments.length) {
      return {
        postId,
        comments: [],
        saved: false,
        skipped: true,
        reason: "No comments found",
      };
    }

    const csv = buildCsv(postId, comments);
    log("csv built", postId, `${comments.length} comments`);

    try {
      log("saving comments", postId);
      const result = await saveViaLocalServer(postId, csv);
      log("saving complete", postId, result.filename);
      return {
        postId,
        comments,
        saved: true,
        method: "server",
        filename: result.filename,
      };
    } catch (error) {
      if (batchMode) {
        throw new Error(
          `Batch mode could not reach the local saver. Restart python save_instagram_comments_server.py and retry. (${error.message})`
        );
      }

      log("local saver unavailable, downloading instead", postId);
      downloadCsv(postId, csv);
      log("download complete", postId);
      return {
        postId,
        comments,
        saved: true,
        method: "download",
        filename: `instagram-comments-${postId}.csv`,
      };
    }
  };

  const waitFor = async (predicate, timeoutMs, label) => {
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      const value = predicate();
      if (value) {
        return value;
      }
      await sleep(250);
    }
    throw new Error(`Timed out waiting for ${label}.`);
  };

  const clickElement = (element) => {
    element.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, cancelable: true }));
    element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
    element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
    element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  };

  const gridPostHrefs = () => {
    const anchors = Array.from(document.querySelectorAll('a[href*="/reel/"], a[href*="/p/"]'));
    const seen = new Set();
    const hrefs = [];

    for (const anchor of anchors) {
      const href = anchor.href;
      if (!href) {
        continue;
      }

      const normalized = normalizePostHref(href);
      if (!normalized) {
        continue;
      }
      if (seen.has(normalized)) {
        continue;
      }

      seen.add(normalized);
      hrefs.push(normalized);
    }

    return hrefs;
  };

  const loadMoreGridItems = async () => {
    let lastCount = 0;
    let stagnantRounds = 0;

    log("loading visible posts from profile grid");
    for (let round = 0; round < batchLoadRounds; round += 1) {
      const currentCount = gridPostHrefs().length;
      log(`grid load round ${round + 1}`, `${currentCount} posts found`);
      if (currentCount <= lastCount) {
        stagnantRounds += 1;
      } else {
        stagnantRounds = 0;
        lastCount = currentCount;
      }

      if (stagnantRounds >= 3) {
        break;
      }

      window.scrollTo(0, document.body.scrollHeight);
      await sleep(batchLoadPauseMs);
    }

    log("grid loading complete");
    window.scrollTo(0, 0);
    await sleep(500);
    const hrefs = gridPostHrefs();
    log("final loaded post count", hrefs.length);
    return hrefs;
  };

  const openOverlayForHref = async (targetHref, index, total) => {
    const candidate = Array.from(document.querySelectorAll('a[href*="/reel/"], a[href*="/p/"]')).find(
      (anchor) => normalizePostHref(anchor.href) === targetHref
    );

    if (!candidate) {
      throw new Error(`Could not find tile for ${targetHref} on the current page.`);
    }

    const beforePath = location.pathname;
    candidate.scrollIntoView({ behavior: "auto", block: "center" });
    await sleep(400);
    log("opening", describePost(targetHref, index, total));
    clickElement(candidate);

    try {
      await waitFor(
        () => overlayDialog() || currentPostId() || location.pathname !== beforePath,
        overlayWaitMs / 2,
        `overlay or route change for ${targetHref}`
      );
    } catch (error) {
      log("anchor click did not open post, trying direct navigation", describePost(targetHref, index, total));
      history.pushState(null, "", targetHref);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }

    await waitFor(
      () => overlayDialog() || currentPostId(),
      overlayWaitMs,
      `overlay for ${targetHref}`
    );
    log("post opened", describePost(targetHref, index, total));
    await sleep(1200);
  };

  const closeOverlay = async () => {
    const dialog = overlayDialog();
    if (!dialog) {
      if (currentPostId()) {
        log("closing post via history back");
        history.back();
        await sleep(1200);
      }
      return;
    }

    const closeButton = Array.from(dialog.querySelectorAll("button, div[role='button']")).find(
      (node) => {
        const aria = (node.getAttribute("aria-label") || "").toLowerCase();
        const text = buttonText(node);
        return /close/.test(aria) || text === "close";
      }
    );

    if (closeButton) {
      log("closing overlay");
      closeButton.click();
    } else {
      log("close button not found, sending escape");
      document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true })
      );
    }

    await waitFor(
      () => !overlayDialog(),
      overlayWaitMs,
      "overlay to close"
    );
    log("overlay closed");
    await sleep(800);
  };

  const runBatchMode = async () => {
    const hrefs = await loadMoreGridItems();
    if (!hrefs.length) {
      throw new Error("No Instagram post/reel tiles were found on this page.");
    }

    const processed = [];
    const skipped = [];

    for (let index = 0; index < hrefs.length; index += 1) {
      const href = hrefs[index];
      log("starting", describePost(href, index, hrefs.length));

      await openOverlayForHref(href, index, hrefs.length);

      try {
        const result = await scrapeCurrentPost({ batchMode: true });
        if (result.skipped) {
          log("skipping", describePost(href, index, hrefs.length), result.reason);
          skipped.push(result);
        } else {
          log("finished", describePost(href, index, hrefs.length), `${result.comments.length} comments saved`);
          processed.push(result);
        }
      } finally {
        await closeOverlay();
      }
    }

    log("batch scrape complete", `saved=${processed.length}`, `skipped=${skipped.length}`);
    alert(
      `Batch scrape finished.\nSaved ${processed.length} posts.\nSkipped ${skipped.length} posts with no recent comments.`
    );
  };

  log(
    "Instagram comment scrape started. Open a post/reel to scrape one item, or run from a profile grid to batch through loaded tiles."
  );

  try {
    if (currentPostId()) {
      const result = await scrapeCurrentPost({ batchMode: false });
      if (result.skipped) {
        alert("No comments were found on the current post/reel.");
      } else if (result.method === "server") {
        alert(`Saved ${result.comments.length} comments to comments/${result.filename}`);
      } else {
        alert(`Downloaded ${result.comments.length} comments.`);
      }
      return;
    }

    await runBatchMode();
  } catch (error) {
    console.error(debugPrefix, error);
    alert(`Instagram bookmarklet failed: ${error?.message || error}`);
  }
})();
