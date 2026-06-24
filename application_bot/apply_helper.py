"""M43: one-click autofill bookmarklet.

Builds a single, reusable browser bookmarklet from the operator's *approved*
contact/identity and answer-bank values. Saved once, it fills the standard
text fields and yes/no questions on an open ATS application page (Greenhouse /
Lever / Ashby and similar), then leaves the rest to the human.

Hard boundaries baked in:
- Only approved, role-independent values are embedded — no fabricated claims,
  and any REVIEW_REQUIRED answer is dropped.
- The bookmarklet NEVER ticks the truthfulness attestation, checks/radios, or
  clicks Submit, and it can't touch file inputs (browsers forbid setting them).
  Résumé upload + attestation + submit stay the human's act.
"""

from __future__ import annotations

import json
from typing import Any

# Sentinel the answer bank uses for "human must answer this personally".
REVIEW_SENTINEL = "REVIEW_REQUIRED"


def _https(value: str) -> str:
    value = (value or "").strip()
    if value and not value.startswith(("http://", "https://")):
        return "https://" + value
    return value


def build_autofill_spec(
    contact: dict[str, Any],
    identity: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Resolve the approved values into a field/yes-no spec for the bookmarklet.

    `answers` is the approved answer draft; anything still REVIEW_REQUIRED is
    excluded so the bookmarklet only ever fills settled, approved values."""
    name = str(identity.get("name") or "").strip()
    first, _, last = name.partition(" ")
    email = str(contact.get("email") or "").strip()
    phone = str(contact.get("phone") or "").strip()
    website = _https(str(contact.get("website") or answers.get("Website") or ""))
    linkedin = _https(str(contact.get("linkedin") or answers.get("LinkedIn") or ""))
    location = str(contact.get("location") or "").strip()
    city = str(contact.get("city") or "").strip()
    state = str(contact.get("state") or "").strip()
    zip_code = str(contact.get("zip") or "").strip()
    street = str(contact.get("street_address") or "").strip()
    company = str(answers.get("Current company") or "").strip()

    # concept, value, label synonyms (matched case-insensitively as substrings).
    raw_fields = [
        ("first_name", first, ["first name", "given name", "legal first"]),
        ("last_name", last, ["last name", "family name", "surname", "legal last"]),
        ("full_name", name, ["full name", "legal name", "candidate name"]),
        ("email", email, ["email", "e-mail"]),
        ("phone", phone, ["phone", "mobile", "telephone", "cell"]),
        ("linkedin", linkedin, ["linkedin"]),
        ("website", website, ["website", "portfolio", "personal site", "web site", "personal website"]),
        ("location", location, ["location", "current location", "based", "city"]),
        ("street", street, ["street address", "address line 1", "mailing address"]),
        ("state", state, ["state/province", "state / province"]),
        ("zip", zip_code, ["zip", "postal code", "postcode"]),
        ("company", company, ["current company", "current employer", "present employer", "present company"]),
    ]
    fields = [
        {"concept": concept, "value": value, "syn": syn}
        for concept, value, syn in raw_fields
        if value
    ]

    # Yes/No questions answered from the approved answer bank (skip if REVIEW).
    yesno: list[dict[str, Any]] = []
    work_auth = str(answers.get("Work authorization") or "")
    if work_auth and REVIEW_SENTINEL not in work_auth:
        yesno.append(
            {
                "concept": "work_authorization",
                "answer": "Yes",
                "syn": [
                    "authorized to work",
                    "legally authorized",
                    "eligible to work",
                    "work authorization",
                ],
            }
        )
    sponsorship = str(answers.get("Sponsorship") or "")
    if sponsorship and REVIEW_SENTINEL not in sponsorship:
        yesno.append(
            {
                "concept": "sponsorship",
                "answer": "No",
                "syn": [
                    "require sponsorship",
                    "need sponsorship",
                    "visa sponsorship",
                    "sponsorship now or in the future",
                    "require visa",
                ],
            }
        )
    return {"fields": fields, "yesno": yesno}


# Single-line bookmarklet body. %s is the JSON spec. No // comments (the URL is
# one line). Sets values via the native setter + input/change events so React/
# Angular forms register them; skips file/hidden/submit/checkbox/radio/password
# and never overwrites a field the human already filled.
#
# `gather` collects fields from the top document AND, recursively, from shadow
# DOM (Workday-style web components) and SAME-ORIGIN iframes. Cross-origin
# iframes (e.g. a careers site embedding job-boards.greenhouse.io) are walled off
# by the browser and can't be reached — open that form in its own tab instead.
_BOOKMARKLET = (
    "javascript:(function(){"
    "var D=%s;"
    "function norm(s){return (s||'').toLowerCase().replace(/\\s+/g,' ').trim();}"
    "function gather(root,acc){try{root.querySelectorAll('input,textarea,select').forEach(function(e){acc.push(e);});"
    "root.querySelectorAll('*').forEach(function(e){if(e.shadowRoot)gather(e.shadowRoot,acc);});"
    "root.querySelectorAll('iframe').forEach(function(f){try{if(f.contentDocument)gather(f.contentDocument,acc);}catch(e){}});}catch(e){}}"
    "function lab(el){var t='';"
    "try{var rn=(el.getRootNode&&el.getRootNode())||document;"
    "if(el.id&&rn.querySelector){var l=rn.querySelector('label[for=\"'+(window.CSS&&CSS.escape?CSS.escape(el.id):el.id)+'\"]');if(l)t+=' '+l.textContent;}}catch(e){}"
    "var p=el.closest&&el.closest('label');if(p)t+=' '+p.textContent;"
    "var w=el.closest&&el.closest('div,fieldset,li');if(w){var wl=w.querySelector('label');if(wl)t+=' '+wl.textContent;}"
    "t+=' '+(el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+((el.getAttribute&&el.getAttribute('aria-label'))||'');return norm(t);}"
    "function setv(el,v){try{var pr=el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;"
    "Object.getOwnPropertyDescriptor(pr,'value').set.call(el,v);}catch(e){el.value=v;}"
    "el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}"
    "var els=[];gather(document,els);var used=[],n=0;"
    "function mark(el){used.push(el);}function isUsed(el){return used.indexOf(el)>=0;}"
    "D.fields.forEach(function(f){for(var i=0;i<els.length;i++){var el=els[i];if(isUsed(el)||el.tagName==='SELECT')continue;"
    "var ty=(el.type||'text').toLowerCase();if(['file','hidden','submit','button','checkbox','radio','password'].indexOf(ty)>=0)continue;"
    "if(el.value&&el.value.trim())continue;var L=lab(el);"
    "if(f.syn.some(function(s){return L.indexOf(s)>=0;})){setv(el,f.value);mark(el);n++;break;}}});"
    "D.yesno.forEach(function(q){els.forEach(function(el){if(isUsed(el))return;var L=lab(el);"
    "if(!q.syn.some(function(s){return L.indexOf(s)>=0;}))return;"
    "if(el.tagName==='SELECT'){for(var i=0;i<el.options.length;i++){if(norm(el.options[i].text)===q.answer.toLowerCase()){"
    "el.selectedIndex=i;el.dispatchEvent(new Event('change',{bubbles:true}));mark(el);n++;return;}}}});});"
    "var b=document.createElement('div');"
    "b.textContent='Autofilled '+n+' field'+(n===1?'':'s')+'. Review, attach your resume from Downloads, tick the box, then submit.';"
    "b.style.cssText='position:fixed;z-index:2147483647;top:16px;right:16px;max-width:320px;background:#10233f;color:#fff;padding:12px 16px;border-radius:10px;font:13px -apple-system,Segoe UI,sans-serif;line-height:1.4;box-shadow:0 8px 30px rgba(0,0,0,.35)';"
    "document.body.appendChild(b);setTimeout(function(){b.remove();},7000);})();"
)


def build_autofill_bookmarklet(
    contact: dict[str, Any],
    identity: dict[str, Any],
    answers: dict[str, Any],
) -> str:
    """Render the full `javascript:` bookmarklet string for the operator."""
    spec = build_autofill_spec(contact, identity, answers)
    return _BOOKMARKLET % json.dumps(spec, separators=(",", ":"))
