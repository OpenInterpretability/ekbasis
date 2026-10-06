"""Resolves every reference of the paper against arXiv (export.arxiv.org API), Crossref or DataCite, and checks that each
software or model URL answers. Where the paper cites a preprint's published venue, the venue is checked on OpenReview
(the venue id of the accepted paper) or on the proceedings page, and the arXiv comment is recorded. Writes
refs_check.json; a reference is kept only if it resolves and its title (and cited venue) match.
    python3 verify_refs.py"""
import json
import re
import time
import urllib.parse
import urllib.request

REFS = [
    # key, kind, id, expected title fragment
    ("chae2025wma", "arxiv", "2410.13232", "Web Agents with World Models"),
    ("gu2025webdreamer", "arxiv", "2411.06559", "Is Your LLM Secretly a World Model of the Internet"),
    ("webworld2026", "arxiv", "2602.14721", "WebWorld"),
    ("zuo2026agentworld", "arxiv", "2606.24597", "Qwen-AgentWorld"),
    ("cwm2025", "arxiv", "2510.02387", "CWM"),
    ("zhang2025early", "arxiv", "2510.08558", "Agent Learning via Early Experience"),
    ("li2026discriminative", "arxiv", "2609.02885", "Discriminative World Models for Web Agents"),
    ("wang2024sim", "doi", "10.18653/v1/2024.acl-short.1", "Can Language Models Serve as Text-Based World Simulators"),
    ("hao2023rap", "doi", "10.18653/v1/2023.emnlp-main.507", "Reasoning with Language Model is Planning with World Model"),
    ("ruan2024toolemu", "arxiv", "2309.15817", "Identifying the Risks of LM Agents"),
    ("kuntz2025osharm", "arxiv", "2506.14866", "OS-Harm"),
    ("levy2024stweb", "arxiv", "2410.06703", "ST-WebAgentBench"),
    ("yao2024tau", "arxiv", "2406.12045", "bench"),
    ("barres2025tau2", "arxiv", "2506.07982", "bench"),
    ("hu2026saber", "arxiv", "2606.01317", "SABER"),
    ("cuadron2025saber", "arxiv", "2512.07850", "SABER"),
    ("cora2026", "arxiv", "2604.09155", "CORA"),
    ("dreamguard2026", "arxiv", "2608.05695", "DreamGuard"),
    ("yu2026seerguard", "arxiv", "2607.15550", "SeerGuard"),
    ("zheng2025webguard", "arxiv", "2507.14293", "WebGuard"),
    ("overeager2026", "arxiv", "2605.18583", "Overeager Coding Agents"),
    ("workbenchrev2026", "arxiv", "2606.13715", "WorkBench Revisited"),
    ("quitting2025", "arxiv", "2510.16492", "Selectively Quitting"),
    ("angelopoulos2021ltt", "arxiv", "2110.01052", "Learn then Test"),
    ("angelopoulos2022crc", "arxiv", "2208.02814", "Conformal Risk Control"),
    ("ren2023knowno", "arxiv", "2307.01928", "Robots That Ask For Help"),
    ("efron1979", "doi", "10.1214/aos/1176344552", "Bootstrap Methods"),
    ("nosek2018", "doi", "10.1073/pnas.1708274114", "preregistration revolution"),
    ("wortsman2022", "doi", "10.1109/CVPR52688.2022.00780", "Robust fine-tuning of zero-shot models"),
    ("wilson1927", "doi", "10.1080/01621459.1927.10502953", "Probable Inference"),
    ("kwon2023vllm", "doi", "10.1145/3600006.3613165", "Efficient Memory Management for Large Language Model Serving"),
    ("vicentino2026ekbasis", "datacite", "10.5281/zenodo.23146970", "Look When Unsure"),
    ("vicentino2026ekbasisv2", "datacite", "10.5281/zenodo.23196358", "Look When Unsure"),
    # software and models: official URLs (must answer)
    ("claudemodels", "url", "https://platform.claude.com/docs/en/models/overview", ""),
    ("claudecode", "url", "https://code.claude.com/docs/en/overview", ""),
    ("glm53", "url", "https://huggingface.co/zai-org/GLM-5.3-Flash", ""),
    ("qwen35", "url", "https://huggingface.co/Qwen/Qwen3.5-4B", ""),
    ("qwen35_9b_url", "url", "https://huggingface.co/Qwen/Qwen3.5-9B", ""),
    ("qwenagentworldmodel", "url", "https://huggingface.co/Qwen/Qwen-AgentWorld-35B-A3B", ""),
    ("gitea", "url", "https://about.gitea.com/", ""),
    ("nextcloud", "url", "https://nextcloud.com/", ""),
    ("roundcube", "url", "https://roundcube.net/", ""),
    ("dms", "url", "https://github.com/docker-mailserver/docker-mailserver", ""),
    ("playwright", "url", "https://playwright.dev/", ""),
    ("opencode", "url", "https://opencode.ai/", ""),
    ("text_url_ekbasis_repo", "url", "https://github.com/OpenInterpretability/ekbasis", ""),
    ("text_url_ekbasis_model", "url", "https://huggingface.co/caiovicentino1/Ekbasis-27B", ""),
]


def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": "ekbasis-paper-refcheck (mailto:caio@openinterp.org)", "Accept": accept})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.read().decode("utf-8", "replace"), r.geturl()


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def arxiv(i):
    _, x, _ = get(f"https://export.arxiv.org/api/query?id_list={i}&max_results=1", "application/atom+xml")
    e = x.split("<entry>")[1]
    title = " ".join(re.search(r"<title>(.*?)</title>", e, re.S).group(1).split())
    authors = re.findall(r"<name>(.*?)</name>", e)
    pub = re.search(r"<published>(.*?)</published>", e).group(1)[:10]
    jref = re.search(r"<arxiv:journal_ref[^>]*>(.*?)</arxiv:journal_ref>", e, re.S)
    doi = re.search(r"<arxiv:doi[^>]*>(.*?)</arxiv:doi>", e, re.S)
    com = re.search(r"<arxiv:comment[^>]*>(.*?)</arxiv:comment>", e, re.S)
    return {"title": title, "first_author": authors[0] if authors else None, "n_authors": len(authors), "authors": authors[:6],
            "year": pub[:4], "published": pub, "journal_ref": jref.group(1).strip() if jref else None, "doi": doi.group(1).strip() if doi else None,
            "arxiv_comment": " ".join(com.group(1).split()) if com else None}


def crossref(d):
    _, x, _ = get(f"https://api.crossref.org/works/{d}")
    m = json.loads(x)["message"]
    a = m.get("author") or []
    dp = (m.get("published") or m.get("issued") or {}).get("date-parts", [[None]])[0]
    return {"title": (m.get("title") or [""])[0], "first_author": f"{a[0].get('given', '')} {a[0].get('family', '')}".strip() if a else None,
            "n_authors": len(a), "year": str(dp[0]) if dp and dp[0] else None, "container": (m.get("container-title") or [""])[0],
            "volume": m.get("volume"), "issue": m.get("issue"), "page": m.get("page"), "doi": m.get("DOI")}


def datacite(d):
    _, x, _ = get(f"https://api.datacite.org/dois/{d}")
    a = json.loads(x)["data"]["attributes"]
    return {"title": (a.get("titles") or [{}])[0].get("title"), "first_author": (a.get("creators") or [{}])[0].get("name"),
            "year": str(a.get("publicationYear")), "publisher": a.get("publisher"), "doi": a.get("doi"),
            "versions": a.get("versionCount"), "version": a.get("version")}


# preprints cited with their published venue: (where to check, what must be found, how the paper cites it)
VENUES = {
    "chae2025wma": ("openreview", "ICLR.cc/2025/Conference", "Proceedings of ICLR, 2025"),
    "kuntz2025osharm": ("openreview", "NeurIPS.cc/2025/Datasets_and_Benchmarks_Track", "NeurIPS Datasets and Benchmarks Track, 2025"),
    "levy2024stweb": ("openreview", "ICLR.cc/2026/Conference", "Proceedings of ICLR, 2026"),
    "zhang2025early": ("openreview", "ICML.cc/2026/Conference", "Proceedings of ICML, 2026"),
    "ren2023knowno": ("pmlr", "https://proceedings.mlr.press/v229/", "PMLR 229:661-682"),
}


def venue(key, title):
    where, what, cited = VENUES[key]
    if where == "openreview":
        _, x, _ = get("https://api2.openreview.net/notes/search?" + urllib.parse.urlencode({"term": title, "limit": 10, "source": "forum"}))
        for n in json.loads(x).get("notes", []):
            c = n.get("content", {})
            t, vid = (c.get("title") or {}).get("value", ""), (c.get("venueid") or {}).get("value", "")
            if norm(t) == norm(title) and vid == what:
                return {"venue_cited": cited, "venue_source": "OpenReview", "venue_found": (c.get("venue") or {}).get("value"),
                        "venueid": vid, "openreview_forum": n.get("forum"), "venue_match": True}
        return {"venue_cited": cited, "venue_source": "OpenReview", "venue_match": False}
    _, x, _ = get(what, "text/html")
    i = norm(x).find(norm(title))
    ctx = norm(x)[i:i + 2000] if i >= 0 else ""
    return {"venue_cited": cited, "venue_source": what, "venue_match": i >= 0 and norm("PMLR 229:661-682") in ctx}


def main():
    out = []
    for key, kind, ident, expect in REFS:
        rec = {"key": key, "kind": kind, "id": ident}
        try:
            if kind == "arxiv":
                rec.update(arxiv(ident))
            elif kind == "doi":
                rec.update(crossref(ident))
            elif kind == "datacite":
                rec.update(datacite(ident))
            else:
                st, body, final = get(ident, "text/html")
                t = re.search(r"<title[^>]*>(.*?)</title>", body, re.S)
                rec.update({"http_status": st, "final_url": final, "page_title": " ".join(t.group(1).split())[:160] if t else None})
            rec["resolved"] = True
            rec["title_match"] = (norm(expect) in norm(rec.get("title") or rec.get("page_title") or "")) if expect else None
            if key in VENUES:
                rec.update(venue(key, rec["title"]))
        except Exception as ex:  # noqa: BLE001
            rec.update({"resolved": False, "error": f"{type(ex).__name__}: {str(ex)[:160]}"})
        out.append(rec)
        print(f"{key:24s} {kind:8s} resolved={rec.get('resolved')} match={rec.get('title_match')} | "
              f"{(rec.get('title') or rec.get('page_title') or rec.get('error') or '')[:90]} | {rec.get('first_author')} {rec.get('year')}", flush=True)
        time.sleep(3.2 if kind == "arxiv" else 0.5)
    tex = open("agents.tex").read()
    cited = sorted({k.strip() for grp in re.findall(r"\\cite\{([^}]+)\}", tex) for k in grp.split(",")})
    for r in out:
        if r["key"] in VENUES:
            item = re.search(r"\\bibitem\{" + re.escape(r["key"]) + r"\}(.*)", tex)
            r["venue_in_bibitem"] = bool(item) and norm(VENUES[r["key"]][2]) in norm(item.group(1))
    keys = {r["key"] for r in out}
    summary = {"cited_keys": len(cited), "cited_without_check": [k for k in cited if k not in keys],
               "all_resolved": all(r.get("resolved") for r in out),
               "all_titles_match": all(r.get("title_match") is not False for r in out),
               "venues_cited_for_preprints": sorted(VENUES),
               "all_venues_match": all(r.get("venue_match") and r.get("venue_in_bibitem") for r in out if r["key"] in VENUES),
               "dropped_unverifiable": ["ToolGuard (no arXiv entry or DOI found under that name)"]}
    json.dump({"summary": summary, "references": out}, open("refs_check.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
