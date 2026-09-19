/*
 * Embeddable multi-agent chat widget.
 *
 * Consumes the gateway's Server-Sent Events contract over fetch (POST /chat) so it works
 * with a bearer/proxy-authenticated gateway. The widget never holds Azure credentials; it
 * only talks to the gateway origin.
 */
(function (global) {
  "use strict";

  const EVENT = {
    SESSION: "session",
    ACTIVITY: "activity",
    TEXT_DELTA: "text_delta",
    CITATIONS: "citations",
    COMPLETED: "completed",
    ERROR: "error",
  };

  function createElement(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
  }

  class ChatWidget {
    constructor(options) {
      if (!options || !options.mount) {
        throw new Error("ChatWidget requires a 'mount' element.");
      }
      this.gatewayUrl = (options.gatewayUrl || "").replace(/\/$/, "");
      this.getHeaders = options.getHeaders || (() => ({}));
      this.sessionId = global.sessionStorage.getItem("map.sessionId") || null;
      this.controller = null;
      this._build(options.mount);
    }

    _build(mount) {
      this.root = createElement("div", "map-widget");
      this.log = createElement("div", "map-log");
      this.log.setAttribute("role", "log");
      this.log.setAttribute("aria-live", "polite");

      this.form = createElement("form", "map-input");
      this.textbox = createElement("input", "map-textbox");
      this.textbox.type = "text";
      this.textbox.placeholder = "Ask a question…";
      this.textbox.setAttribute("aria-label", "Message");
      this.send = createElement("button", "map-send", "Send");
      this.send.type = "submit";
      this.cancel = createElement("button", "map-cancel", "Stop");
      this.cancel.type = "button";
      this.cancel.hidden = true;

      this.form.append(this.textbox, this.send, this.cancel);
      this.root.append(this.log, this.form);
      mount.append(this.root);

      this.form.addEventListener("submit", (e) => {
        e.preventDefault();
        this._submit();
      });
      this.cancel.addEventListener("click", () => this._abort());
    }

    async _submit() {
      const text = this.textbox.value.trim();
      if (!text || this.controller) return;
      this.textbox.value = "";
      this._appendMessage("user", text);
      const assistant = this._appendMessage("assistant", "");
      this._setBusy(true);

      this.controller = new AbortController();
      try {
        await this._stream(text, assistant);
      } catch (err) {
        if (err.name !== "AbortError") {
          assistant.textContent = "Something went wrong. Please try again.";
        }
      } finally {
        this._setBusy(false);
        this.controller = null;
      }
    }

    async _stream(text, assistant) {
      const response = await fetch(this.gatewayUrl + "/chat", {
        method: "POST",
        headers: Object.assign(
          { "Content-Type": "application/json" },
          this.getHeaders()
        ),
        body: JSON.stringify({ text: text, session_id: this.sessionId }),
        signal: this.controller.signal,
      });
      if (!response.ok || !response.body) {
        assistant.textContent = "The assistant is unavailable (" + response.status + ").";
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";
        for (const block of blocks) {
          this._handleEvent(block, assistant);
        }
      }
    }

    _handleEvent(block, assistant) {
      const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
      if (!dataLine) return;
      let event;
      try {
        event = JSON.parse(dataLine.slice("data: ".length));
      } catch (_) {
        return;
      }
      switch (event.type) {
        case EVENT.SESSION:
          this.sessionId = event.session_id;
          global.sessionStorage.setItem("map.sessionId", event.session_id);
          break;
        case EVENT.ACTIVITY:
          this._setStatus(event.activity);
          break;
        case EVENT.TEXT_DELTA:
          assistant.textContent += event.text || "";
          this._scroll();
          break;
        case EVENT.CITATIONS:
          this._renderCitations(assistant, event.citations || []);
          break;
        case EVENT.COMPLETED:
          this._setStatus(null);
          break;
        case EVENT.ERROR:
          assistant.textContent =
            (event.error && event.error.message) || "An error occurred.";
          this._setStatus(null);
          break;
      }
    }

    _renderCitations(assistant, citations) {
      if (!citations.length) return;
      const list = createElement("ul", "map-citations");
      for (const c of citations) {
        const item = createElement("li");
        const label = c.title || c.source_id;
        if (c.url) {
          const link = createElement("a", null, label);
          link.href = c.url;
          link.target = "_blank";
          link.rel = "noopener";
          item.append(link);
        } else {
          item.textContent = label;
        }
        list.append(item);
      }
      assistant.parentElement.append(list);
    }

    _appendMessage(role, text) {
      const wrapper = createElement("div", "map-message map-" + role);
      const bubble = createElement("div", "map-bubble", text);
      wrapper.append(bubble);
      this.log.append(wrapper);
      this._scroll();
      return bubble;
    }

    _setStatus(activity) {
      if (!activity) {
        if (this.status) {
          this.status.remove();
          this.status = null;
        }
        return;
      }
      if (!this.status) {
        this.status = createElement("div", "map-status");
        this.log.append(this.status);
      }
      this.status.textContent = activity.agent + ": " + activity.action + "…";
      this._scroll();
    }

    _setBusy(busy) {
      this.send.disabled = busy;
      this.cancel.hidden = !busy;
      this.textbox.disabled = busy;
      if (!busy) this.textbox.focus();
    }

    _abort() {
      if (this.controller) this.controller.abort();
    }

    _scroll() {
      this.log.scrollTop = this.log.scrollHeight;
    }
  }

  global.MultiAgentChat = {
    mount: function (options) {
      return new ChatWidget(options);
    },
  };
})(window);
