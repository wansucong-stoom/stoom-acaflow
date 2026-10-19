"""Offline public route memory. No statistics, credentials, or network requests.

Seed references are read-only. Mutations go to the caller's workspace (or
ACADEMYINFO_FLOW_STATE_DIR), never an installed plugin cache. A successful
catalog lookup proves availability only, not report/attachment support.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import uuid

FORMAT = "academyinfo-flow-route-registry-v1"
SEED = Path(__file__).resolve().parents[1] / "references" / "query-routes.json"
if not SEED.is_file():
    SEED = Path(__file__).resolve().parent / 'references' / 'query-routes.json'
OFFICIAL_HOSTS = {"academyinfo.go.kr", "www.academyinfo.go.kr", "m.academyinfo.go.kr"}
ARCHIVE_HOST = "hannam-regulations-wiki.esceeee.chatgpt.site"
ARCHIVE_HOSTS = {ARCHIVE_HOST, "h-rules.stoom.win"}
CATALOG_PATH = "/main/main0780/selectItemList.do"
REPORT_PATHS = {"/NewAcInfo.do", "/NewAcInfo2.do", "/UbiServer.do"}
BOOTSTRAP_PATH = "/uipnh/unt/unmcom/RdViewer.do"
INIT_DEFAULTS = {"paramMjrItem1": "00", "paramMjrItem2": "00", "paramMjrItem3": "00",
                 "paramSchlKindCd": "99", "paramSchlEstabCd": "99", "paramDomainDiv": "MOB"}
FILE_CATALOG_PATH = "/main/main0830/selectGongsiDataList.do"
FILE_DOWNLOAD_PATH = "/main/main0830/FileDown.do"
LIVE_COMMANDS = {"scope", "schools", "affiliations", "departments", "metric", "info",
                 "catalog", "report", "attachments", "pdf", "file_catalog", "file_download",
                 "route_observation", "archive_list", "archive_query", "archive_versions", "archive_export"}
PUBLIC_PARAMETERS = {
    "svyYr", "svy_yr", "pubYear", "schlDivCd", "schl_div_cd", "schoolDivision",
    "itemId", "item_id", "level", "language", "reqtype", "flag", "searchGbn",
    "category_cd", "category_gubun", "searchVal", "searchValue", "pbnf_area_cd",
    "pageindex", "pageIndex", "pageIdx", "schlId", "schlMjrId", "mjrId",
    "schlMjrIdSe", "schlIdSe", "mjrIdSe", "mjrIdDt", "tabSelect", "std_dta_div_cd",
    "file_nm", "file_path", "file_dtl_nm", "filePath", "fileName", "saveName",
    "datasetId", "snapshotId", "schoolCode", "departmentCode", "disclosureYear",
    "basisYear", "basisPeriod", "indicator", "limit", "offset", "query",
    "publicationYear", "referenceYear", "referencePeriod", "surveyYear", "degree", "unitStatus",
    "schoolType", "term", "detailGroup", "school", "includeFilters",
    "paramSvyYr", "paramSchlDivCd", "paramItemId", "paramFormClftCd", "paramMjrItem1",
    "paramMjrItem2", "paramMjrItem3", "paramSchlKindCd", "paramSchlEstabCd", "paramDomainDiv",
    "paramSchlCd", "paramZoneCd", "formClassification",
}
YEAR_KEYS = {"svyYr", "svy_yr", "pubYear", "paramSvyYr", "publicationYear"}
DIVISION_KEYS = {"schlDivCd", "schl_div_cd", "schoolDivision", "paramSchlDivCd"}
ITEM_KEYS = {"itemId", "item_id", "paramItemId"}
PRIVATE_VALUE = re.compile(
    r"(?:\b(?:select\s+.+?\s+from|insert\s+into|delete\s+from|update\s+\S+\s+set)\b|"
    r"\b(?:bearer|authorization|cookie|session|password|pkey|parg|ubikey|ubiargs)\s*[:=]|"
    r"<\s*(?:html|script|body)|https?://)", re.I)
SAFE_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class RegistryError(ValueError):
    """Error messages contain no source values or local/private payloads."""


def _text(value: Any, maximum: int = 512) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    value = str(value)
    if len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    if PRIVATE_VALUE.search(value):
        return None
    return value


def _time(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def public_url(value: Any, *, archive: bool = False) -> str | None:
    """Only retain stable endpoint paths; queries/fragments are never stored."""
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parts = urlsplit(value)
        hosts = ARCHIVE_HOSTS if archive else OFFICIAL_HOSTS
        if (parts.scheme != "https" or parts.hostname not in hosts or parts.username
                or parts.password or parts.port not in {None, 443}
                or ".." in parts.path
                or re.search(r"[\x00-\x20\\]", parts.path)):
            return None
        # Stable public POST initialization is separate from a generated page.
        if "rdviewer" in parts.path.lower() and (parts.path != BOOTSTRAP_PATH or parts.query or parts.fragment):
            return None
        if archive and not (parts.path in {"/api/disclosures", "/api/disclosures/query",
                                         "/api/disclosures/versions"}
                            or re.fullmatch(r"/exports/disclosures/[a-z0-9-]+\.(csv|md|json)", parts.path)):
            return None
        return urlunsplit(("https", parts.hostname, parts.path or "/", "", ""))
    except ValueError:
        return None


def public_parameters(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    safe = {}
    for key in sorted(PUBLIC_PARAMETERS.intersection(value)):
        item = (str(value[key]).lower() if key == "includeFilters" and isinstance(value[key], bool)
                else _text(value[key]))
        if item is None:
            continue
        if key in YEAR_KEYS and not re.fullmatch(r"\d{4}", item):
            continue
        if key in DIVISION_KEYS and item not in {"01", "02", "03", "04"}:
            continue
        if key in ITEM_KEYS and not re.fullmatch(r"\d{1,6}", item):
            continue
        if key == "level" and item not in {"school", "department"}:
            continue
        if key in {'paramSchlCd', 'schoolCode'} and not re.fullmatch(r'[0-9]{7}', item):
            continue
        safe[key] = item
    return safe


def empty_registry() -> dict[str, Any]:
    return {"format": FORMAT, "purpose": "Public route metadata only; no statistical values or runtime state",
            "catalog": [], "routes": [], "families": []}


def family_key(method: str, url: str, parameters: dict[str, str]) -> str:
    return _digest([method, url, sorted(parameters)])[:20]


def _scope(parameters: dict[str, str]) -> dict[str, str]:
    scope = {}
    for target, keys in (("year", YEAR_KEYS), ("division", DIVISION_KEYS), ("item_id", ITEM_KEYS)):
        values = {parameters[k] for k in keys if k in parameters}
        if len(values) == 1:
            scope[target] = next(iter(values))
    if "level" in parameters:
        scope["level"] = parameters["level"]
    elif parameters.get("paramFormClftCd") in {"30", "36", "60"}:
        scope["level"] = "department" if parameters["paramFormClftCd"] in {"36", "60"} else "school"
    school = parameters.get('paramSchlCd') or parameters.get('schoolCode')
    if school:
        scope['school_code'] = school
    if parameters.get('paramFormClftCd') == '60' or parameters.get('formClassification') == '60':
        scope['form'] = '60'
    return scope


def _route(registry: dict, kind: str, method: str, url: str, parameters: dict,
           *, title: str | None = None, item_id: str | None = None,
           code: str | None = None) -> dict:
    identity = {k: v for k, v in parameters.items() if kind != "official_download" or k not in {"searchValue", "searchVal"}}
    route_id = _digest([kind, method, url, identity])[:24]
    found = next((r for r in registry["routes"] if r["route_id"] == route_id), None)
    if found is None:
        found = {"route_id": route_id, "kind": kind, "method": method, "url": url,
                 "public_parameters": parameters, "parameter_keys": sorted(parameters),
                 "family_id": family_key(method, url, parameters), "scope": _scope(parameters),
                 "titles": [], "status": "candidate", "support_verified": False,
                 "observations": [], "last_success": None, "latest_observation": None}
        registry["routes"].append(found)
    safe_title = _text(title)
    if safe_title and safe_title not in found["titles"]:
        found["titles"].append(safe_title)
    if item_id and re.fullmatch(r"\d{1,6}", item_id):
        found["item_id"] = item_id
    if code and SAFE_CODE.fullmatch(code):
        found["download_code"] = code
    if kind == "official_download" and safe_title:
        found["scope"].setdefault("level", "department" if "학과별" in safe_title else "school")
        found["level_basis"] = "file_title_hint"
        period = re.search(r"(?<!\d)(20\d{2})\s*[~–-]\s*(20\d{2})(?!\d)", safe_title)
        if period:
            found["file_period_hint"] = {"from": period[1], "until": period[2], "basis": "official_file_title"}
    return found


def _observe(route: dict, status: str, source: dict, *, observed_utc: str | None = None,
             basis: str = "live_output") -> bool:
    if status not in {"success", "partial", "failure", "catalog_confirmed"}:
        raise RegistryError("지원하지 않는 관측 상태입니다.")
    stamp = _time(observed_utc or source.get("retrieved_utc"))
    if stamp is None:
        raise RegistryError("관측 시각은 시간대가 있는 ISO 8601 값이어야 합니다.")
    observation = {"observed_utc": stamp, "status": status, "evidence_basis": basis}
    http = source.get("response_status")
    if isinstance(http, int) and not isinstance(http, bool) and 100 <= http <= 599:
        observation["http_status"] = http
    sha = source.get("raw_sha256")
    if isinstance(sha, str) and re.fullmatch(r"[a-fA-F0-9]{64}", sha):
        observation["raw_sha256"] = sha.lower()
    content_type = _text(source.get("response_content_type"), 120)
    if content_type:
        observation["content_type"] = content_type
    if source.get("hash_scope") in {"raw_response", "saved_json_serialization", "preserved_source_file"}:
        observation["hash_scope"] = source["hash_scope"]
    observation["observation_id"] = _digest([route["route_id"], observation])[:24]
    if any(o["observation_id"] == observation["observation_id"] for o in route["observations"]):
        return False
    observation["recorded_sequence"] = max((o.get("recorded_sequence", index + 1)
        for index, o in enumerate(route["observations"])), default=0) + 1
    route["observations"].append(observation)
    # UTC orders actual source observations. Ingestion sequence resolves a
    # corrected observation at the same instant, never a random hash order.
    route["observations"].sort(key=lambda o: (o["observed_utc"], o.get("recorded_sequence", 0)))
    route["latest_observation"] = copy.deepcopy(route["observations"][-1])
    successes = [o for o in route["observations"] if o["status"] == "success"
                 or route["kind"] in {"catalog", "file_catalog"} and o["status"] == "catalog_confirmed"]
    route["last_success"] = copy.deepcopy(successes[-1]) if successes else None
    route["support_verified"] = bool(successes) and route["kind"] not in {"catalog", "file_catalog"}
    route["status"] = {"success": "verified", "failure": "failed", "partial": "partial",
                       "catalog_confirmed": "catalog_confirmed"}[route["latest_observation"]["status"]]
    return True


def _catalog_source(source: Any) -> tuple[str, str] | None:
    if not isinstance(source, dict):
        return None
    url = public_url(source.get("source_url"))
    stamp = _time(source.get("retrieved_utc") or source.get("fetched_at"))
    if url and urlsplit(url).path == CATALOG_PATH and stamp:
        return url, stamp
    return None


def import_catalog(registry: dict, payload: dict) -> int:
    """Copy allowlisted catalog fields, never numeric rows from other commands."""
    candidates = []
    if payload.get("format") == "academyinfo-flow-catalog-reference-v1":
        scopes = {}
        for catalog in payload.get("catalogs", []):
            evidence = _catalog_source(catalog.get("source"))
            if evidence:
                scopes[f"{catalog.get('year')}/{catalog.get('division')}"] = evidence
        for row in payload.get("entries", []):
            for scope in row.get("available_in", []):
                if scope in scopes:
                    year, division = scope.split("/")
                    candidates.append((row, year, division, *scopes[scope]))
    elif payload.get("command") == "catalog" and payload.get("status") == "ok" and payload.get("complete") is True:
        sources = [s for s in payload.get("sources", []) if _catalog_source(s)
                   and isinstance(s.get("response_status"), int) and 200 <= s["response_status"] < 300]
        if sources:
            url, stamp = _catalog_source(sources[-1])
            params = public_parameters(sources[-1].get("public_parameters"))
            year, division = params.get("svyYr"), params.get("schlDivCd")
            for row in payload.get("rows", []):
                if (str(row.get("svy_yr")) == year and str(row.get("schl_div_cd")) == division):
                    candidates.append((row, year, division, url, stamp))
    count = 0
    for row, year, division, url, stamp in candidates:
        item = _text(row.get("item_id"), 6)
        title = _text(row.get("title") or row.get("pgm_estn_nm"))
        levels = row.get("viewer_levels") or row.get("supported_request_levels")
        if levels is None:
            step = _text(row.get("mjr_use_step_cd"), 3)
            levels = ["school", "department"] if step and step != "0" else ["school"]
        levels = [level for level in levels if level in {"school", "department"}] if isinstance(levels, list) else []
        if (not item or not re.fullmatch(r"\d{1,6}", item) or not title or not levels
                or not isinstance(year, str) or not re.fullmatch(r"\d{4}", year)
                or division not in {"01", "02", "03", "04"}):
            continue
        key = (item, year, division)
        found = next((c for c in registry["catalog"] if (c["item_id"], c["year"], c["division"]) == key), None)
        if found is None:
            found = {"item_id": item, "year": year, "division": division, "titles": [],
                     "levels": levels, "pdf_only": row.get("pdf_use_yn") == "Y",
                     "catalog_url": url, "catalog_seen_utc": stamp}
            registry["catalog"].append(found)
            count += 1
        if title not in found["titles"]:
            found["titles"].append(title)
        if stamp >= found["catalog_seen_utc"]:
            found.update(levels=levels, pdf_only=row.get("pdf_use_yn") == "Y", catalog_seen_utc=stamp)
    registry["catalog"].sort(key=lambda c: (int(c["item_id"]), c["year"], c["division"]))
    return count


def import_manifest(registry: dict, payload: dict) -> int:
    count = 0
    for record in payload.get("results", []):
        request = record.get("downloadRequest", {})
        url = public_url(request.get("url"))
        method = request.get("method")
        if not url or method not in {"GET", "POST"}:
            continue
        params = public_parameters(request.get("form"))
        # This import is limited to independently preserved official downloads.
        if urlsplit(url).path != FILE_DOWNLOAD_PATH or not params.get("std_dta_div_cd"):
            continue
        item = record.get("sourceItem", {})
        route = _route(registry, "official_download", method, url, params,
                       title=params.get("file_nm"), item_id=_text(item.get("item_id"), 6),
                       code=_text(record.get("code"), 80))
        steps = [s for s in record.get("steps", []) if s.get("action") == "download"]
        http = steps[-1].get("status") if steps else None
        sha = record.get("sourceSha256") or record.get("summary", {}).get("sourceSha256")
        success = bool(record.get("success") is True and (http is None or isinstance(http, int) and 200 <= http < 300)
                       and isinstance(sha, str) and re.fullmatch(r"[a-fA-F0-9]{64}", sha))
        source = {"response_status": http, "raw_sha256": sha,
                  "hash_scope": "preserved_source_file",
                  "retrieved_utc": record.get("retrievedAt") or record.get("completedAt")}
        created = _text(item.get("file_crtn_stt_dtm"), 10)
        if created and re.fullmatch(r"\d{4}-\d{2}-\d{2}", created):
            route["file_created_date"] = created
        if _time(source["retrieved_utc"]):
            state = "success" if success and http is not None else "partial" if success else "failure"
            route["preserved_file_verified"] = success
            count += _observe(route, state, source, basis="preserved_download_manifest" if http is not None
                              else "preserved_file_manifest_transport_unverified")
    return count


def import_file_catalog(registry: dict, payload: dict) -> int:
    """Retain only file route metadata from a complete official file catalog."""
    if (payload.get("command") != "file_catalog" or payload.get("status") != "ok"
            or payload.get("complete") is not True
            or payload.get("completeness", {}).get("source_complete") is not True):
        return 0
    sources = [s for s in payload.get("sources", []) if isinstance(s, dict)
               and public_url(s.get("source_url"))
               and urlsplit(public_url(s["source_url"])).path == FILE_CATALOG_PATH
               and isinstance(s.get("response_status"), int) and 200 <= s["response_status"] < 300
               and _time(s.get("retrieved_utc"))]
    if not sources:
        return 0
    source = sources[-1]
    count = 0
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        params = public_parameters({"schl_div_cd": row.get("accm_schl_div_cd"), "searchValue": "",
            "file_nm": row.get("file_nm"), "file_path": row.get("file_pth_nm"),
            "file_dtl_nm": row.get("file_dtl_nm"), "std_dta_div_cd": row.get("std_dta_div_cd")})
        if (len(params) != 6 or not re.fullmatch(r"[0-9]{3}", params["std_dta_div_cd"])
                or not re.fullmatch(r"/infofile/SCHEDULER/EXCEL/", params["file_path"])
                or not re.fullmatch(r"[A-Za-z0-9_.-]+\.xlsx", params["file_dtl_nm"], re.I)):
            continue
        route = _route(registry, "official_download", "POST", "https://www.academyinfo.go.kr" + FILE_DOWNLOAD_PATH,
                       params, title=params["file_nm"], item_id=_text(row.get("item_id"), 6),
                       code=params["std_dta_div_cd"])
        created = _text(row.get("file_crtn_stt_dtm"), 10)
        if created and re.fullmatch(r"\d{4}-\d{2}-\d{2}", created):
            route["file_created_date"] = created
        route["catalog_evidence"] = {"url": public_url(source["source_url"]),
                                      "observed_utc": _time(source["retrieved_utc"])}
        route["catalog_status"] = "listed_recipe"
        route.pop("superseded_by", None)
        route.pop("superseded_utc", None)
        for previous in registry["routes"]:
            if (previous is not route and previous["kind"] == "official_download"
                    and previous.get("download_code") == route.get("download_code")
                    and previous.get("scope", {}).get("division") == route["scope"].get("division")):
                older = previous.get("catalog_evidence", {}).get("observed_utc")
                if not older or older <= route["catalog_evidence"]["observed_utc"]:
                    previous["catalog_status"] = "superseded_recipe"
                    previous["superseded_by"] = route["route_id"]
                    previous["superseded_utc"] = route["catalog_evidence"]["observed_utc"]
        if re.fullmatch(r"[a-fA-F0-9]{64}", str(source.get("raw_sha256", ""))):
            route["catalog_evidence"]["sha256"] = source["raw_sha256"].lower()
            route["catalog_evidence"]["hash_scope"] = source.get("hash_scope", "raw_response") if source.get("hash_scope", "raw_response") in {
                "raw_response", "saved_json_serialization"} else "unspecified"
        # The catalog hash validates selection metadata; it is not a file-body hash.
        count += _observe(route, "catalog_confirmed", {"retrieved_utc": source["retrieved_utc"]},
                          basis="official_file_catalog_metadata")
    return count


def record_result(registry: dict, payload: dict, *, route_id: str | None = None,
                  observed_utc: str | None = None) -> int:
    """Consume live_json/live_report/live_batch metadata; rows are never retained."""
    if payload.get("command") == "batch" and isinstance(payload.get("results"), list):
        return sum(record_result(registry, r, observed_utc=observed_utc)
                   for r in payload["results"] if isinstance(r, dict))
    if payload.get("command") == "catalog":
        import_catalog(registry, payload)
    if payload.get("command") == "file_catalog":
        import_file_catalog(registry, payload)
    status = payload.get("status")
    complete = payload.get("complete") is True
    source_complete = payload.get("completeness", {}).get("source_complete") is True
    outcome = "success" if (payload.get("command") in LIVE_COMMANDS and status == "ok"
                            and complete and source_complete) else (
        "partial" if status == "partial" else "failure")
    count = 0
    seen_target = False
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        url = public_url(source.get("source_url")) or public_url(source.get("source_url"), archive=True)
        method = source.get("method")
        if not url or method not in {"GET", "POST"}:
            continue
        params = public_parameters(source.get("public_parameters"))
        is_catalog = urlsplit(url).path == CATALOG_PATH
        is_file_catalog = urlsplit(url).path == FILE_CATALOG_PATH
        is_report = urlsplit(url).path in REPORT_PATHS
        is_download = urlsplit(url).path == FILE_DOWNLOAD_PATH
        is_init = urlsplit(url).path == BOOTSTRAP_PATH
        if ((is_init and params.get('paramFormClftCd') == '60' and not params.get('paramSchlCd'))
                or (is_report and params.get('formClassification') == '60' and not params.get('schoolCode'))):
            continue  # Never remember a school-specific recipe without its school identity.
        if is_init and (method != "POST" or not (set(params) & YEAR_KEYS and set(params) & ITEM_KEYS)):
            continue
        is_archive = urlsplit(url).hostname in ARCHIVE_HOSTS
        kind = ("archive" if is_archive else "catalog" if is_catalog else "file_catalog" if is_file_catalog else "report_bootstrap" if is_init
                else "live_report" if is_report else "official_download" if is_download else "live_json")
        query = payload.get("query", {})
        selected = payload.get("selected_file", {})
        item = params.get("itemId") or params.get("paramItemId") or _text(query.get("item"), 6) or _text(selected.get("item_id"), 6)
        title = payload.get("catalog_item", {}).get("pgm_estn_nm") if is_report or is_init else params.get("file_nm") if is_download else None
        route = _route(registry, kind, method, url, params, title=title, item_id=item,
                       code=params.get("std_dta_div_cd") if is_download else None)
        if route_id and route["route_id"] != route_id:
            continue
        http = source.get("response_status")
        valid_transport = (isinstance(http, int) and not isinstance(http, bool) and 200 <= http < 300
                           and re.fullmatch(r"[a-fA-F0-9]{64}", str(source.get("raw_sha256", ""))))
        state = "catalog_confirmed" if (is_catalog or is_file_catalog) and valid_transport else outcome
        if not valid_transport:
            state = "failure"
        # A catalog cannot prove another command's report support.
        if (is_catalog or is_file_catalog) and outcome != "success":
            state = "partial" if outcome == "partial" else "failure"
        if _time(observed_utc or source.get("retrieved_utc")):
            count += _observe(route, state, source, observed_utc=observed_utc)
            seen_target = True
        verified = payload.get("verified_scope", {})
        if (is_download and outcome == "success" and valid_transport and isinstance(verified, dict)
                and verified.get("evidence") == "file_contents"):
            years = verified.get("years")
            if isinstance(years, list) and 0 < len(years) <= 100 and all(
                    isinstance(y, str) and re.fullmatch(r"(?:19|20)\d{2}", y) for y in years):
                route["verified_years"] = sorted(set(years))
                route["body_scope_verified"] = True
                route["body_scope_complete"] = verified.get("complete") is True
                route["body_scope_observed_utc"] = _time(observed_utc or source.get("retrieved_utc"))
            if verified.get("level") in {"school", "department"}:
                route["scope"]["level"] = verified["level"]
                route["level_basis"] = "verified_file_contents"
    # Failed attempts may return no source exchange at all. The explicit
    # command's shipped endpoint is a known route, not a guessed endpoint.
    error = payload.get("error", {})
    query = payload.get("query", {})
    command = payload.get("command")
    attempted_listing = command == "file_catalog" or command == "file_download" and error.get("phase") == "catalog"
    if (not route_id and outcome != "success" and attempted_listing
            and error.get("code") in {"source_connection_error", "source_validation_error", "source_http_error"}
            and query.get("division") in {"01", "02", "03", "04"}
            and not any(isinstance(s, dict) and public_url(s.get("source_url"))
                        and urlsplit(public_url(s["source_url"])).path == FILE_CATALOG_PATH for s in payload.get("sources", []))):
        params = public_parameters({"schl_div_cd": query["division"], "searchValue": query.get("keyword", "") if command == "file_catalog" else ""})
        route = _route(registry, "file_catalog", "POST", "https://www.academyinfo.go.kr" + FILE_CATALOG_PATH, params)
        count += _observe(route, "failure", {}, observed_utc=observed_utc or payload.get("retrieved_utc")
                          or payload.get("lookup_started_utc") or _now(), basis="known_command_attempt")
    if route_id and not seen_target:
        route = next((r for r in registry["routes"] if r["route_id"] == route_id), None)
        if route is None or outcome == "success":
            raise RegistryError("경로 증거 없는 성공 기록 또는 알 수 없는 경로 ID입니다.")
        count += _observe(route, outcome, {}, observed_utc=observed_utc or payload.get("retrieved_utc"))
    return count


def learn_families(registry: dict) -> int:
    """Generalize only method + official host/path + public parameter-key schema."""
    families = {}
    for route in registry["routes"]:
        if route["kind"] == "archive":
            continue
        fid = route["family_id"]
        family = families.setdefault(fid, {"family_id": fid, "method": route["method"],
            "url": route["url"], "parameter_keys": route["parameter_keys"],
            "route_count": 0, "verified_route_count": 0, "substitution_keys": [],
            "candidate_only": True})
        family["route_count"] += 1
        if route["support_verified"]:
            family["verified_route_count"] += 1
            family["candidate_only"] = False
        family["substitution_keys"] = sorted(set(route["parameter_keys"]) & (YEAR_KEYS | DIVISION_KEYS | ITEM_KEYS))
    registry["families"] = sorted(families.values(), key=lambda f: f["family_id"])
    return len(families)


def _catalog_candidates(registry: dict, catalog: dict, level: str) -> list[dict]:
    """Generate candidates from confirmed catalog values, never invented IDs/years."""
    output = []
    families = [f for f in registry["families"] if not f["candidate_only"]
                and urlsplit(f["url"]).path in REPORT_PATHS | {BOOTSTRAP_PATH}]
    if not families:
        families = [{"method": "POST", "url": "https://academyinfo.go.kr/NewAcInfo.do",
                     "parameter_keys": ["pubYear", "schoolDivision", "itemId", "level", "language"],
                     "family_id": "bundled_protocol_candidate", "candidate_only": True}]
    for family in families:
        templates = [r for r in registry["routes"] if r["family_id"] == family["family_id"] and r["support_verified"]]
        if templates:
            params = dict(templates[-1]["public_parameters"])
        else:
            params = {"pubYear": catalog["year"], "schoolDivision": catalog["division"],
                      "itemId": catalog["item_id"], "level": level, "language": "ko"}
        if not (set(params) & YEAR_KEYS and set(params) & DIVISION_KEYS and set(params) & ITEM_KEYS):
            continue
        for key in set(params) & YEAR_KEYS:
            params[key] = catalog["year"]
        for key in set(params) & DIVISION_KEYS:
            params[key] = catalog["division"]
        for key in set(params) & ITEM_KEYS:
            params[key] = catalog["item_id"]
        if "level" in params:
            params["level"] = level
        is_init = urlsplit(family["url"]).path == BOOTSTRAP_PATH
        if is_init and "paramFormClftCd" in params:
            params["paramFormClftCd"] = "36" if level == "department" else "30"
        # Never transfer school/dept codes, page offsets, or file selectors to another item.
        permitted = YEAR_KEYS | DIVISION_KEYS | ITEM_KEYS | {"level", "language", "reqtype"}
        if is_init:
            permitted |= set(INIT_DEFAULTS) | {"paramFormClftCd"}
            if any(params.get(k, default) != default for k, default in INIT_DEFAULTS.items()):
                continue
        if set(params) - permitted:
            continue
        kind = "report_bootstrap" if is_init else "live_report"
        output.append({"route_id": _digest([kind, family["method"], family["url"], params])[:24],
            "kind": kind, "method": family["method"], "url": family["url"],
            "public_parameters": params, "scope": {"year": catalog["year"], "division": catalog["division"],
                "item_id": catalog["item_id"], "level": level}, "item_id": catalog["item_id"],
            "titles": catalog["titles"], "status": "candidate", "support_verified": False,
            "candidate_basis": "verified_family_and_catalog" if templates else "bundled_protocol_and_catalog",
            "catalog_seen_utc": catalog["catalog_seen_utc"], "last_success": None, "latest_observation": None,
            "command": "attachments" if catalog["pdf_only"] else "report"})
    return output


def lookup(registry: dict, *, keyword: str = "", item: str | None = None, year: str | None = None,
           division: str | None = None, level: str | None = None, kind: str | None = None,
           since: str | None = None, until: str | None = None, limit: int = 10) -> dict:
    if not 1 <= limit <= 100:
        raise RegistryError("반환 제한은 1~100입니다.")
    bounds = [_time(v) if v else None for v in (since, until)]
    if any(raw and parsed is None for raw, parsed in zip((since, until), bounds)):
        raise RegistryError("시간 필터는 시간대가 있는 ISO 8601 값이어야 합니다.")
    if bounds[0] and bounds[1] and bounds[0] > bounds[1]:
        raise RegistryError("시작 시각은 종료 시각 이후일 수 없습니다.")
    routes = copy.deepcopy(registry["routes"])
    known = {r["route_id"] for r in routes}
    for catalog in registry["catalog"]:
        for target_level in catalog["levels"]:
            for candidate in _catalog_candidates(registry, catalog, target_level):
                if candidate["route_id"] not in known:
                    routes.append(candidate)
                    known.add(candidate["route_id"])
    matches = []
    for route in routes:
        scope = route.get("scope", {})
        period_unverified = False
        year_matches = not year or scope.get("year") == year
        if year and route["kind"] == "official_download" and not scope.get("year"):
            confirmed = route.get("verified_years")
            hint = route.get("file_period_hint")
            if confirmed:
                year_matches = year in confirmed or route.get("body_scope_complete") is not True
                period_unverified = year not in confirmed and year_matches
            elif hint:
                year_matches = hint["from"] <= year <= hint["until"]
                period_unverified = year_matches
            else:
                year_matches = True
                period_unverified = True
        if (item and (route.get("item_id") or scope.get("item_id")) != item
                or not year_matches or division and scope.get("division") != division
                or level and scope.get("level") != level or kind and route["kind"] != kind):
            continue
        if keyword and keyword.casefold() not in " ".join(route.get("titles", [])).casefold():
            continue
        latest = route.get("latest_observation") or {}
        stamp = latest.get("observed_utc") or route.get("catalog_seen_utc")
        if bounds[0] and (not stamp or stamp < bounds[0]) or bounds[1] and (not stamp or stamp > bounds[1]):
            continue
        view = {k: route[k] for k in ("route_id", "kind", "method", "url", "public_parameters", "scope",
            "titles", "status", "support_verified", "last_success", "latest_observation") if k in route}
        for key in ("candidate_basis", "catalog_seen_utc", "command", "item_id", "download_code", "links",
                    "file_created_date", "catalog_evidence"):
            if key in route:
                view[key] = route[key]
        view["observation_count"] = len(route.get("observations", []))
        for key in ("file_period_hint", "level_basis", "verified_years", "body_scope_verified", "body_scope_complete", "preserved_file_verified"):
            if key in route:
                view[key] = route[key]
        for key in ("catalog_status", "superseded_by", "body_scope_observed_utc"):
            if key in route:
                view[key] = route[key]
        if period_unverified:
            view["scope_matches"] = "unverified"
            view["scope_note"] = "요청 연도의 본문 범위는 미확인입니다. 실제 파일의 기간 열을 확인하세요."
        if route["kind"] == "live_report":
            view["execution"] = "live_report_adapter_required; public selectors are not ephemeral wire parameters"
        elif route["kind"] == "report_bootstrap":
            view["execution"] = "public_bootstrap_then_live_report_adapter"
        matches.append(view)
    matches.sort(key=lambda r: (r.get("catalog_status") == "superseded_recipe", not r["support_verified"], r.get("scope", {}).get("year", ""),
                               r["titles"][0] if r["titles"] else "", r["route_id"]))
    return {"status": "ok", "mode": "offline_metadata", "total_matches": len(matches),
            "returned_count": min(limit, len(matches)), "routes": matches[:limit],
            "note": "후보는 지원 확정이 아닙니다. 현재 공식 목록과 실제 조회로 검증하며 수치는 새로 조회합니다."}


def add_archive_links(registry: dict) -> None:
    """Known archive endpoints are navigation references, not official live evidence."""
    ids = []
    for host in sorted(ARCHIVE_HOSTS):
        for path, title in (("/api/disclosures", "보존 통계 목록"),
                            ("/api/disclosures/query", "보존 통계 조건 조회"),
                            ("/api/disclosures/versions", "보존 통계 버전")):
            route = _route(registry, "archive", "GET", f"https://{host}{path}", {}, title=title)
            if not route["observations"]:
                route["status"] = "reference_only"
            route["links"] = {"export_pattern": f"https://{host}/exports/disclosures/{{datasetId}}.json",
                              "host_identity_verified": False}
            ids.append(route["route_id"])
    for route in registry["routes"]:
        if route["kind"] == "official_download":
            route["links"] = {"archive_route_ids": ids}


def import_payload(registry: dict, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise RegistryError("입력 JSON은 객체여야 합니다.")
    if "results" in payload and "sourcePage" in payload:
        count = import_manifest(registry, payload)
        add_archive_links(registry)
        category = "preserved_download_manifest"
    elif payload.get("format") == "academyinfo-flow-catalog-reference-v1" or payload.get("command") == "catalog":
        count = import_catalog(registry, payload)
        category = "official_catalog_metadata"
    elif payload.get("command") == "file_catalog":
        count = import_file_catalog(registry, payload)
        category = "official_file_catalog_metadata"
    else:
        raise RegistryError("지원하는 import는 기존 다운로드 manifest와 공식 catalog JSON입니다.")
    learn_families(registry)
    return {"status": "ok", "import_kind": category, "added_count": count,
            "route_count": len(registry["routes"]), "catalog_scope_count": len(registry["catalog"])}


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise RegistryError("입력 JSON 파일을 읽을 수 없습니다.") from error
    if not isinstance(value, dict):
        raise RegistryError("입력 JSON은 객체여야 합니다.")
    return value


def load_registry(state_file: Path, seed: Path = SEED) -> dict:
    """Merge new seed metadata even when a caller already has a state file.

    Existing observations are replayed first and remain intact. A corrected
    seed observation at the same UTC comes later; duplicates are idempotent.
    The read-only merge is persisted only by a subsequent mutation/hook.
    """
    merged = empty_registry()
    inputs = []
    if state_file.exists():
        inputs.append(read_json(state_file))
    if seed.exists() and seed.resolve() != state_file.resolve():
        inputs.append(read_json(seed))
    for incoming in inputs:
        if (incoming.get("format") != FORMAT or not all(isinstance(incoming.get(k), list)
                                                        for k in ("routes", "catalog", "families"))):
            raise RegistryError("경로 레지스트리 형식을 확인할 수 없습니다.")
        for entry in incoming["catalog"]:
            if not isinstance(entry, dict):
                continue
            evidence = _catalog_source({"source_url": entry.get("catalog_url"),
                                        "retrieved_utc": entry.get("catalog_seen_utc")})
            item, year, division = entry.get("item_id"), entry.get("year"), entry.get("division")
            if (not evidence or not isinstance(item, str) or not re.fullmatch(r"\d{1,6}", item)
                    or not isinstance(year, str) or not re.fullmatch(r"\d{4}", year)
                    or division not in {"01", "02", "03", "04"}):
                continue
            for title in entry.get("titles", []):
                if not _text(title):
                    continue
                import_catalog(merged, {"format": "academyinfo-flow-catalog-reference-v1",
                    "catalogs": [{"year": year, "division": division, "source": {
                        "source_url": evidence[0], "retrieved_utc": evidence[1]}}],
                    "entries": [{"item_id": item, "title": title, "available_in": [year + "/" + division],
                        "viewer_levels": entry.get("levels", []), "pdf_use_yn": "Y" if entry.get("pdf_only") else "N"}]})
        for source_route in incoming["routes"]:
            if not isinstance(source_route, dict):
                continue
            kind = source_route.get("kind")
            if kind not in {"official_download", "live_report", "report_bootstrap", "live_json", "catalog", "file_catalog", "archive"}:
                continue
            url = public_url(source_route.get("url"), archive=kind == "archive")
            method = source_route.get("method")
            if not url or method not in {"GET", "POST"}:
                continue
            params = public_parameters(source_route.get("public_parameters"))
            target = _route(merged, kind, method, url, params, item_id=_text(source_route.get("item_id"), 6),
                            code=_text(source_route.get("download_code"), 80))
            for title in source_route.get("titles", []):
                _route(merged, kind, method, url, params, title=title)
            for obs in source_route.get("observations", []):
                if not isinstance(obs, dict) or obs.get("status") not in {"success", "failure", "partial", "catalog_confirmed"}:
                    continue
                if not _time(obs.get("observed_utc")):
                    continue
                _observe(target, obs["status"], {"response_status": obs.get("http_status"),
                    "raw_sha256": obs.get("raw_sha256"), "response_content_type": obs.get("content_type"),
                    "hash_scope": obs.get("hash_scope")}, observed_utc=obs["observed_utc"],
                    basis=_text(obs.get("evidence_basis"), 80) or "stored_public_observation")
            if source_route.get("preserved_file_verified") is True:
                target["preserved_file_verified"] = True
            created = _text(source_route.get("file_created_date"), 10)
            if created and re.fullmatch(r"\d{4}-\d{2}-\d{2}", created):
                target["file_created_date"] = created
            catalog_evidence = source_route.get("catalog_evidence", {})
            superseded_stamp = _time(source_route.get("superseded_utc"))
            if superseded_stamp and superseded_stamp >= target.get("superseded_utc", ""):
                superseded = source_route.get("superseded_by")
                if isinstance(superseded, str) and re.fullmatch(r"[a-f0-9]{24}", superseded):
                    target["catalog_status"] = "superseded_recipe"
                    target["superseded_by"] = superseded
                    target["superseded_utc"] = superseded_stamp
            existing_catalog_utc = target.get("catalog_evidence", {}).get("observed_utc", "")
            if (isinstance(catalog_evidence, dict) and public_url(catalog_evidence.get("url"))
                    and _time(catalog_evidence.get("observed_utc"))
                    and _time(catalog_evidence["observed_utc"]) >= existing_catalog_utc):
                target["catalog_evidence"] = {"url": public_url(catalog_evidence["url"]),
                    "observed_utc": _time(catalog_evidence["observed_utc"])}
                if re.fullmatch(r"[a-fA-F0-9]{64}", str(catalog_evidence.get("sha256", ""))):
                    target["catalog_evidence"]["sha256"] = catalog_evidence["sha256"].lower()
                    target["catalog_evidence"]["hash_scope"] = catalog_evidence.get("hash_scope", "unspecified") if catalog_evidence.get("hash_scope") in {
                        "raw_response", "saved_json_serialization"} else "unspecified"
                if source_route.get("catalog_status") in {"listed_recipe", "superseded_recipe"}:
                    target["catalog_status"] = source_route["catalog_status"]
                superseded = source_route.get("superseded_by")
                if isinstance(superseded, str) and re.fullmatch(r"[a-f0-9]{24}", superseded):
                    target["superseded_by"] = superseded
            years = source_route.get("verified_years")
            body_stamp = _time(source_route.get("body_scope_observed_utc"))
            if (target["last_success"] and source_route.get("body_scope_verified") is True
                    and body_stamp and body_stamp >= target.get("body_scope_observed_utc", "")
                    and isinstance(years, list) and 0 < len(years) <= 100
                    and all(isinstance(y, str) and re.fullmatch(r"(?:19|20)\d{2}", y) for y in years)):
                target["verified_years"] = sorted(set(years))
                target["body_scope_verified"] = True
                target["body_scope_complete"] = source_route.get("body_scope_complete") is True
                target["body_scope_observed_utc"] = body_stamp
                if source_route.get("level_basis") == "verified_file_contents" and source_route.get("scope", {}).get("level") in {"school", "department"}:
                    target["scope"]["level"] = source_route["scope"]["level"]
                    target["level_basis"] = "verified_file_contents"
    if any(r["kind"] in {"official_download", "archive"} for r in merged["routes"]):
        add_archive_links(merged)
    learn_families(merged)
    return merged


def state_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    directory = os.environ.get("ACADEMYINFO_FLOW_STATE_DIR")
    return ((Path(directory) if directory else Path.cwd() / ".academyinfo-flow-state") / "routes.json").resolve()


def save_registry(registry: dict, destination: Path) -> None:
    destination = destination.resolve()
    normalized = destination.as_posix().lower()
    if re.search(r"/(?:\.codex|\.claude)/plugins/cache/", normalized):
        raise RegistryError("설치된 플러그인 캐시는 수정하지 않습니다. 작업 폴더의 상태 경로를 지정하세요.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # A single exclusive UUID file fails promptly on permission denial.
        # Windows tempfile can retry PermissionError thousands of times when
        # os.access reports a directory writable but the host sandbox denies it.
        temporary = destination.parent / (".routes-" + uuid.uuid4().hex + ".tmp")
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(registry, stream, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def observe_result(result: dict, state_file: str | Path | None = None) -> dict:
    """Best-effort CLI hook; persistence failure must not change query success.

    Kept separate from pure query functions. This accepts only the same public
    output metadata as ``record`` and never copies the returned numeric rows.
    """
    if os.environ.get("ACADEMYINFO_FLOW_DISABLE_ROUTE_RECORD") == "1":
        return {"recorded": False, "route_count": 0, "warning": "환경변수로 경로 기록이 비활성화되어 있습니다."}
    try:
        destination = state_path(str(state_file) if state_file is not None else None)
        current = load_registry(destination)
        count = record_result(current, result)
        learn_families(current)
        if count:
            save_registry(current, destination)
        return {"recorded": bool(count), "route_count": len(current["routes"])}
    except (RegistryError, OSError, TypeError, KeyError, ValueError):
        return {"recorded": False, "route_count": 0,
                "warning": "경로 기록을 저장하지 못했습니다. 원천 조회 결과와 마지막 성공 기록은 변경하지 않습니다."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("lookup", "record", "import", "learn"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--state-file", help="상태 JSON 경로; 기본은 caller workspace")
        cmd.add_argument("--seed", type=Path, default=SEED, help="읽기 전용 초기 경로 메타데이터")
        if name in {"record", "import"}:
            cmd.add_argument("--input", type=Path, required=True)
        if name == "record":
            cmd.add_argument("--route-id", help="source 없는 실패를 기존 경로와 연결할 때만 사용")
            cmd.add_argument("--observed-utc")
        if name == "learn":
            cmd.add_argument("--catalog", type=Path, help="이미 확보한 공식 catalog JSON; 새 네트워크 없음")
        if name == "lookup":
            cmd.add_argument("--keyword", default="")
            cmd.add_argument("--item")
            cmd.add_argument("--year")
            cmd.add_argument("--division", choices=["01", "02", "03", "04"])
            cmd.add_argument("--level", choices=["school", "department"])
            cmd.add_argument("--kind", choices=["official_download", "live_report", "report_bootstrap", "live_json", "catalog", "archive"])
            cmd.add_argument("--since")
            cmd.add_argument("--until")
            cmd.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        path = state_path(args.state_file)
        registry = load_registry(path, args.seed)
        if args.command == "lookup":
            result = lookup(registry, **{k: getattr(args, k) for k in (
                "keyword", "item", "year", "division", "level", "kind", "since", "until", "limit")})
        elif args.command == "import":
            result = import_payload(registry, read_json(args.input))
        elif args.command == "record":
            count = record_result(registry, read_json(args.input), route_id=args.route_id,
                                  observed_utc=args.observed_utc)
            learn_families(registry)
            result = {"status": "ok", "added_observations": count, "route_count": len(registry["routes"])}
        else:
            if args.catalog:
                import_catalog(registry, read_json(args.catalog))
            result = {"status": "ok", "family_count": learn_families(registry),
                      "note": "패턴 후보는 공식 catalog에서 확인한 item ID/연도/기관 값으로만 lookup에 생성합니다."}
        if args.command != "lookup":
            save_registry(registry, path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RegistryError, OSError, TypeError, KeyError) as error:
        # No source exception/payload/private value is echoed.
        message = str(error) if isinstance(error, RegistryError) else "경로 메타데이터 처리에 실패했습니다."
        print(json.dumps({"status": "error", "error": {"code": "route_registry_error", "message": message}},
                         ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
