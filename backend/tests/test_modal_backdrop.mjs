import assert from "node:assert";

class MockElement {
  constructor(id = "", className = "") {
    this.id = id;
    this.className = className;
    this.children = [];
    this.parentElement = null;
    this._listeners = {};
    this.classList = {
      _classes: new Set(className.split(" ").filter(Boolean)),
      contains(cls) { return this._classes.has(cls); },
      add(cls) { this._classes.add(cls); },
      remove(cls) { this._classes.delete(cls); }
    };
  }

  get firstElementChild() {
    return this.children[0] || null;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  querySelector(selector) {
    if (selector.startsWith("#")) {
      const targetId = selector.slice(1);
      if (this.id === targetId) return this;
      for (const child of this.children) {
        const found = child.querySelector(selector);
        if (found) return found;
      }
    }
    return null;
  }

  contains(el) {
    if (!el) return false;
    if (el === this) return true;
    let curr = el.parentElement;
    while (curr) {
      if (curr === this) return true;
      curr = curr.parentElement;
    }
    return false;
  }

  addEventListener(type, cb) {
    if (!this._listeners[type]) this._listeners[type] = [];
    this._listeners[type].push(cb);
  }

  dispatchEvent(event) {
    const listeners = this._listeners[event.type] || [];
    for (const cb of listeners) {
      cb(event);
    }
    if (event.bubbles && this.parentElement) {
      this.parentElement.dispatchEvent(event);
    }
  }
}

// Build mock modal hierarchy
const elements = {};
function getElementById(id) {
  return elements[id] || null;
}

const historyModal = new MockElement("history-modal", "fixed inset-0");
const historyCard = new MockElement("history-card", "bg-surface");
const insideBtn = new MockElement("inside-btn", "btn");
historyCard.appendChild(insideBtn);
historyModal.appendChild(historyCard);

elements["history-modal"] = historyModal;
elements["history-card"] = historyCard;
elements["inside-btn"] = insideBtn;

let historyClosed = false;

function setupModalBackdropDismiss(modalId, closeFn) {
  const modal = getElementById(modalId);
  if (!modal) return;
  modal.addEventListener("click", (e) => {
    const innerCard = modal.querySelector("#modal-content-wrap") || modal.firstElementChild;
    if (innerCard && !innerCard.contains(e.target)) {
      closeFn();
    }
  });
}

setupModalBackdropDismiss("history-modal", () => { historyClosed = true; });

// 1. Click inside history modal card -> must NOT close
insideBtn.dispatchEvent({ type: "click", target: insideBtn, bubbles: true });
assert.strictEqual(historyClosed, false, "Clicking inside history modal should not close it");

// 2. Click outside on the backdrop -> MUST close
historyModal.dispatchEvent({ type: "click", target: historyModal, bubbles: false });
assert.strictEqual(historyClosed, true, "Clicking on history modal backdrop should close it");

console.log("Mock modal backdrop dismiss checks: 100% PASSED!");
