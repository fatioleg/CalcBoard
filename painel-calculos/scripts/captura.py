#!/usr/bin/env python3
"""captura.py — confere o painel num navegador headless e salva capturas de tela.

Uso
  python captura.py painel.html -o captura.png                      página inteira
  python captura.py painel.html -o zoom.png --hash "#zoom=<id>"      abre direto no modo Ampliar
  python captura.py painel.html -o s.png --secao s_energia --altura 900   só uma seção (rola até ela)

Ordem de preferência: (1) Playwright + Chromium (WebGL por software: o 3D aparece; relata erros de JavaScript);
(2) Firefox via WebDriver BiDi (relata erros; o 3D depende de o Firefox headless ter WebGL na máquina; precisa do pacote
`websockets`); (3) Chrome/Chromium/Edge com --screenshot (sem relato de erros).
Saída: código 0 se a página carregou sem erros de JavaScript; 2 se houve erros (listados); 3 se não há navegador.
"""
import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CHROMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "microsoft-edge-stable", "msedge"]


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def _bidi(url, saida, largura, altura, secao, espera, tema, js_extra, avaliar=None):
    import websockets
    porta = porta_livre()
    perfil = tempfile.mkdtemp(prefix="painel_ff_")
    Path(perfil, "user.js").write_text('user_pref("webgl.force-enabled", true);\nuser_pref("webgl.disabled", false);\nuser_pref("webgl.enable-webgl2", true);\nuser_pref("webgl.disable-fail-if-major-performance-caveat", true);\nuser_pref("gfx.webrender.software", true);\nuser_pref("webgl.out-of-process", false);\nuser_pref("security.sandbox.content.level", 0);\nuser_pref("gfx.blocklist.all", -1);\n' + os.environ.get("PAINEL_FF_PREFS", "") + '\nuser_pref("browser.shell.checkDefaultBrowser", false);\n'
                                       'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n', encoding="utf-8")
    ff = shutil.which("firefox")
    proc = subprocess.Popen([ff, "--headless", f"--remote-debugging-port={porta}", "--profile", perfil, "--no-remote"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws = None
        for _ in range(120):
            try:
                ws = await websockets.connect(f"ws://127.0.0.1:{porta}/session", max_size=2 ** 28)
                break
            except Exception:
                await asyncio.sleep(0.25)
        if ws is None:
            raise RuntimeError("Firefox não abriu a porta de depuração")
        n = [0]
        logs = []

        async def cmd(metodo, params):
            n[0] += 1
            meu = n[0]
            await ws.send(json.dumps({"id": meu, "method": metodo, "params": params}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("type") == "event" or m.get("method") == "log.entryAdded":
                    if m.get("method") == "log.entryAdded":
                        p = m["params"]
                        logs.append((p.get("level"), p.get("text") or str(p.get("args"))))
                    continue
                if m.get("id") == meu:
                    if m.get("type") == "error" or "error" in m and m.get("type") != "success":
                        raise RuntimeError(f"{metodo}: {m.get('error')} {m.get('message')}")
                    return m.get("result", {})

        await cmd("session.new", {"capabilities": {}})
        await cmd("session.subscribe", {"events": ["log.entryAdded"]})
        ctx = (await cmd("browsingContext.create", {"type": "tab"}))["context"]
        await cmd("browsingContext.setViewport", {"context": ctx, "viewport": {"width": largura, "height": altura}})
        if tema:
            await cmd("browsingContext.navigate", {"context": ctx, "url": url.split("#")[0], "wait": "complete"})
            await cmd("script.evaluate", {"expression": f"localStorage.clear(); document.documentElement.setAttribute('data-theme','{tema}');", "target": {"context": ctx}, "awaitPromise": False})
        await cmd("browsingContext.navigate", {"context": ctx, "url": url, "wait": "complete"})
        if tema:
            await cmd("script.evaluate", {"expression": f"document.documentElement.setAttribute('data-theme','{tema}'); redesenharTudo();", "target": {"context": ctx}, "awaitPromise": False})
        for _ in range(int(espera * 4)):
            r = await cmd("script.evaluate", {"expression": "window.__pronto === true", "target": {"context": ctx}, "awaitPromise": False})
            if r.get("result", {}).get("value"):
                break
            await asyncio.sleep(0.25)
        await asyncio.sleep(1.5)
        if js_extra:
            await cmd("script.evaluate", {"expression": js_extra, "target": {"context": ctx}, "awaitPromise": False})
            await asyncio.sleep(1.5)
        if secao:
            await cmd("script.evaluate", {"expression": f"document.getElementById('{secao}').scrollIntoView(); window.scrollBy(0,-50);", "target": {"context": ctx}, "awaitPromise": False})
            await asyncio.sleep(1.0)
        r = await cmd("script.evaluate", {"expression": "JSON.stringify(window.__erros || [])", "target": {"context": ctx}, "awaitPromise": False})
        erros = json.loads(r.get("result", {}).get("value") or "[]")
        if avaliar:
            r = await cmd("script.evaluate", {"expression": f"JSON.stringify({avaliar})", "target": {"context": ctx}, "awaitPromise": False})
            print("avaliar:", r.get("result", {}).get("value"))
        origem = "viewport" if (secao or js_extra or "#zoom" in url) else "document"
        shot = await cmd("browsingContext.captureScreenshot", {"context": ctx, "origin": origem})
        Path(saida).write_bytes(base64.b64decode(shot["data"]))
        erros += [t for (lv, t) in logs if lv == "error"]
        await ws.close()
        return erros
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        shutil.rmtree(perfil, ignore_errors=True)


def via_playwright(url, saida, largura, altura, secao, espera, tema, js_extra, avaliar=None):
    from playwright.sync_api import sync_playwright
    erros = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": largura, "height": altura})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        if tema:
            pg.add_init_script(f"try{{localStorage.setItem('painel_tema_forcado','{tema}')}}catch(e){{}}; document.documentElement.setAttribute('data-theme','{tema}');")
        pg.goto(url, wait_until="load")
        try:
            pg.wait_for_function("window.__pronto === true", timeout=espera * 1000)
        except Exception:
            erros.append("o painel não sinalizou __pronto")
        pg.wait_for_timeout(1500)
        if tema:
            pg.evaluate(f"document.documentElement.setAttribute('data-theme','{tema}'); redesenharTudo();")
            pg.wait_for_timeout(800)
        if js_extra:
            pg.evaluate(js_extra)
            pg.wait_for_timeout(1800)
        if secao:
            pg.evaluate(f"document.getElementById('{secao}').scrollIntoView(); window.scrollBy(0,-50);")
            pg.wait_for_timeout(1200)
        erros += pg.evaluate("window.__erros || []")
        if avaliar:
            print("avaliar:", json.dumps(pg.evaluate(avaliar), ensure_ascii=False)[:2000])
        inteira = not (secao or js_extra or "#zoom" in url)
        pg.screenshot(path=saida, full_page=inteira)
        b.close()
    return list(dict.fromkeys(erros))


def via_chrome(url, saida, largura, altura):
    for nome in CHROMES:
        exe = shutil.which(nome)
        if exe:
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--use-angle=swiftshader", f"--window-size={largura},{altura}",
                            "--virtual-time-budget=15000", f"--screenshot={os.path.abspath(saida)}", url],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            return Path(saida).exists()
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="captura headless do painel")
    ap.add_argument("html")
    ap.add_argument("-o", "--saida", default="captura.png")
    ap.add_argument("--largura", type=int, default=1400)
    ap.add_argument("--altura", type=int, default=900)
    ap.add_argument("--hash", default="")
    ap.add_argument("--secao", default=None, help="id da seção para enquadrar (ex.: s_energia)")
    ap.add_argument("--tema", choices=["light", "dark"], default=None)
    ap.add_argument("--js", default=None, help="JavaScript a executar antes da captura (ex.: abrir o modo Ampliar)")
    ap.add_argument("--espera", type=float, default=30)
    ap.add_argument("--avaliar", default=None, help="expressão JavaScript cujo valor (JSON) é impresso")
    a = ap.parse_args(argv)
    url = Path(a.html).resolve().as_uri() + a.hash
    erros = None
    try:
        import playwright  # noqa: F401
        erros = via_playwright(url, a.saida, a.largura, a.altura, a.secao, a.espera, a.tema, a.js, a.avaliar)
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        print("Playwright falhou:", str(e)[:300])
    if erros is None and shutil.which("firefox"):
        try:
            import websockets  # noqa: F401
            erros = asyncio.run(_bidi(url, a.saida, a.largura, a.altura, a.secao, a.espera, a.tema, a.js, a.avaliar))
        except ImportError:
            erros = None
        except Exception as e:  # noqa: BLE001
            print("Firefox/BiDi falhou:", e)
            erros = None
    if erros is None:
        if not via_chrome(url, a.saida, a.largura, a.altura):
            print("nenhum navegador headless disponível (Firefox com websockets, ou Chrome/Chromium/Edge)")
            sys.exit(3)
        print(f"{a.saida} (Chrome/Edge; erros de JavaScript não verificados)")
        return
    print(f"{a.saida}  ({len(erros)} erro(s) de JavaScript)")
    for e in erros:
        print("  JS:", e)
    sys.exit(2 if erros else 0)


if __name__ == "__main__":
    main()
