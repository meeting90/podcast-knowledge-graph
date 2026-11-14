/**
 * podcast-knowledge-graph — Pi extension.
 *
 * The work is done by the bundled Python package (`skills/podcast-knowledge-graph/lib/podcast_kg`, CLI name
 * `podcast-kg`). This file is the Pi-side bridge and does four things:
 *
 *   1. prepares a private Python environment with **all** dependencies
 *      (`uv pip install "<root>[all]"`) the first time a session starts, then
 *      puts a `podcast-kg` shim on PATH for the bash tool;
 *   2. appends `.pi/APPEND_SYSTEM.md` to the system prompt (CLI is `--help`-driven);
 *   3. contributes the bundled skill from `skills/`;
 *   4. exposes `/podcast-kg` for environment checks (`/podcast-kg doctor`).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = path.resolve(HERE, "..", "..");
const SKILLS_DIR = path.join(PACKAGE_ROOT, "skills");
const APPEND_FILE = path.join(PACKAGE_ROOT, ".pi", "APPEND_SYSTEM.md");
const MARKER = "podcast-kg";

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR || path.join(os.homedir(), ".pi", "agent");
const CACHE_DIR = path.join(AGENT_DIR, "cache", "podcast-kg");
const VENV_DIR = path.join(CACHE_DIR, "venv");
const BIN_DIR = path.join(CACHE_DIR, "bin");
const IS_WIN = process.platform === "win32";

type Ready = { ok: boolean; cli?: string; python?: string; note: string };

let ready: Ready | undefined;
let booting: Promise<Ready> | undefined;

const log = (message: string) => console.error(`[podcast-kg] ${message}`);

function pathKey(): string {
	return Object.keys(process.env).find((k) => k.toLowerCase() === "path") ?? "PATH";
}

function pathEntries(): string[] {
	return (process.env[pathKey()] ?? "").split(path.delimiter).filter(Boolean);
}

function isFile(candidate: string): boolean {
	try {
		return fs.statSync(candidate).isFile();
	} catch {
		return false;
	}
}

function samePath(a: string, b: string): boolean {
	return path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();
}

/** Our own shim directory must never be treated as a real installation. */
function isShimDir(dir: string): boolean {
	return samePath(dir, BIN_DIR);
}

function findOnPath(name: string, extraDirs: string[] = []): string | undefined {
	const exts = IS_WIN ? [".exe", ".cmd", ".bat", ""] : [""];
	// PATH first (a real uv tool / pipx / PATH install wins), then extra dirs.
	// BIN_DIR is skipped so a shim can never be mistaken for the CLI it points at.
	for (const dir of [...pathEntries(), ...extraDirs]) {
		if (isShimDir(dir)) continue;
		for (const ext of exts) {
			const candidate = path.join(dir, name + ext);
			if (isFile(candidate)) return candidate;
		}
	}
	return undefined;
}

function venvBin(name: string): string {
	return path.join(VENV_DIR, IS_WIN ? "Scripts" : "bin", name);
}

function findUv(): string | undefined {
	const configured = process.env.PODCAST_KG_UV?.trim();
	if (configured && isFile(configured)) return configured;
	return findOnPath("uv", [
		path.join(os.homedir(), ".local", "bin"),
		path.join(os.homedir(), ".cargo", "bin"),
	]);
}

function findSystemPython(): string | undefined {
	for (const name of IS_WIN ? ["python", "python3"] : ["python3", "python"]) {
		const found = findOnPath(name);
		if (found) return found;
	}
	return undefined;
}

function prependToPath(dir: string): void {
	const key = pathKey();
	const current = process.env[key] ?? "";
	const normalize = (p: string) => path.resolve(p).toLowerCase();
	const parts = current.split(path.delimiter).filter(Boolean);
	if (!parts.some((p) => normalize(p) === normalize(dir))) {
		process.env[key] = [dir, ...parts].join(path.delimiter);
	}
}

type RunResult = { code: number; stderr: string };

/**
 * Run a command without streaming its output.
 *
 * `capture` keeps the tail of stderr so a failed boot can report the real
 * reason: with `stdio: "ignore"` the only thing we ever learned was
 * "退出码 2", which is not actionable from the user side.
 */
function run(command: string, args: string[], capture = false): Promise<RunResult> {
	return new Promise((resolve) => {
		const child = spawn(command, args, {
			stdio: ["ignore", "ignore", capture ? "pipe" : "ignore"],
			windowsHide: true,
		});
		let stderr = "";
		child.stderr?.on("data", (chunk: Buffer | string) => {
			stderr = (stderr + chunk.toString()).slice(-2000);
		});
		child.on("error", (error) => {
			log(`${command} failed: ${error.message}`);
			resolve({ code: -1, stderr: error.message });
		});
		child.on("close", (code) => resolve({ code: code ?? -1, stderr: stderr.trim() }));
	});
}

/** One-line failure reason: exit code plus the last stderr lines. */
function failure(step: string, result: RunResult): string {
	const tail = result.stderr
		.split("\n")
		.map((line) => line.trim())
		.filter(Boolean)
		.slice(-2)
		.join(" ");
	return `${step}（退出码 ${result.code}${tail ? `：${tail}` : ""}）`;
}

const POSIX_SHIM = path.join(BIN_DIR, "podcast-kg");
const WIN_SHIM = path.join(BIN_DIR, "podcast-kg.cmd");

/** Write only when the content changed; never throw (a locked file must not kill Pi). */
function writeIfChanged(file: string, content: string): boolean {
	try {
		if (isFile(file) && fs.readFileSync(file, "utf8") === content) return true;
	} catch {
		// unreadable/locked: fall through and try to replace it
	}
	const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
	try {
		fs.writeFileSync(tmp, content, "utf8");
		fs.renameSync(tmp, file);
		return true;
	} catch (error) {
		try {
			fs.unlinkSync(tmp);
		} catch {
			// best effort
		}
		log(`无法写入 shim ${file}：${error instanceof Error ? error.message : String(error)}`);
		return false;
	}
}

function writeShim(cliPath: string): void {
	// A shim that points at itself recurses forever: `podcast-kg.cmd` spawns
	// `podcast-kg.cmd` … Keep that broken state unrepresentable.
	if (samePath(cliPath, POSIX_SHIM) || samePath(cliPath, WIN_SHIM)) {
		log(`拒绝写入自我指向的 shim（目标是它自己）：${cliPath}`);
		return;
	}
	try {
		fs.mkdirSync(BIN_DIR, { recursive: true });
	} catch (error) {
		log(`无法创建 ${BIN_DIR}：${error instanceof Error ? error.message : String(error)}`);
		return;
	}
	const posix = `#!/bin/sh\n# Generated by the podcast-knowledge-graph Pi extension.\nexec '${cliPath.replace(/'/g, "'\\''")}' "$@"\n`;
	if (writeIfChanged(POSIX_SHIM, posix) && !IS_WIN) {
		try {
			fs.chmodSync(POSIX_SHIM, 0o755);
		} catch {
			// best effort
		}
	}
	if (IS_WIN) writeIfChanged(WIN_SHIM, `@echo off\r\n"${cliPath}" %*\r\n`);
}

/**
 * Make the Python CLI available. Everything (CLI + faster-whisper)
 * is installed into a private venv on first run, so later sessions are instant.
 */
async function ensureEnvironment(): Promise<Ready> {
	if (ready) return ready;

	// 1) An existing install wins: a `uv tool`/pipx/PATH `podcast-kg`, or the
	//    venv a previous Pi session prepared.
	const venvCli = isFile(venvBin("podcast-kg.exe")) ? venvBin("podcast-kg.exe") : isFile(venvBin("podcast-kg")) ? venvBin("podcast-kg") : undefined;
	const existing = findOnPath("podcast-kg") ?? venvCli;
	if (existing) {
		writeShim(existing);
		prependToPath(BIN_DIR);
		ready = { ok: true, cli: existing, note: `复用已安装的 CLI: ${existing}` };
		return ready;
	}

	// 2) Build the private venv.
	const uv = findUv();
	const python = findSystemPython();
	if (!uv && !python) {
		ready = {
			ok: false,
			note: "未找到 uv 或 Python。安装 uv（https://docs.astral.sh/uv/）后重开 Pi。",
		};
		return ready;
	}

	log("首次运行：正在准备 Python 环境并安装依赖（faster-whisper）…");
	try {
		fs.mkdirSync(CACHE_DIR, { recursive: true });
		const venvPython = venvBin(IS_WIN ? "python.exe" : "python");
		// Booting has to be safe to repeat. `uv venv` exits 2 whenever the
		// directory already exists, which used to brick every later session: a
		// first-run install failure left a half-built venv behind, and every
		// retry died at "创建 venv 失败（退出码 2）" before it could write the shim.
		// So only create when the interpreter is missing, and clear a broken one.
		if (!isFile(venvPython)) {
			const version = process.env.PODCAST_KG_PYTHON_VERSION || "3.12";
			const created = uv
				? await run(uv, ["venv", VENV_DIR, "--python", version, "--seed", "--quiet", "--clear"], true)
				: await run(python!, ["-m", "venv", "--clear", VENV_DIR], true);
			if (created.code !== 0) throw new Error(failure("创建 venv 失败", created));
		}

		// The non-uv branch used to slice off "-m" and run `<python> pip install`,
		// i.e. execute a file named `pip`; both branches now pass the same args.
		const installArgs = uv
			? ["pip", "install", "--python", venvPython, `${PACKAGE_ROOT}[all]`]
			: ["-m", "pip", "install", "--quiet", `${PACKAGE_ROOT}[all]`];
		const installed = uv
			? await run(uv, installArgs, true)
			: await run(venvPython, installArgs, true);
		if (installed.code !== 0) throw new Error(failure("安装 podcast-kg[all] 失败", installed));

		const cli = isFile(venvBin("podcast-kg.exe")) ? venvBin("podcast-kg.exe") : venvBin("podcast-kg");
		if (!isFile(cli)) throw new Error("安装完成但找不到 podcast-kg 可执行文件");

		writeShim(cli);
		prependToPath(BIN_DIR);
		ready = {
			ok: true,
			cli,
			python: venvPython,
			note: `依赖已就绪（venv: ${VENV_DIR}）`,
		};
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		log(message);
		ready = {
			ok: false,
			// "运行 podcast-kg doctor" is circular advice here: that is exactly
			// the thing that is missing. Point at the cache, which repairs it.
			note: `环境准备失败：${message}。删掉 ${CACHE_DIR} 后重开 Pi 可重建。`,
		};
	}
	return ready;
}

function ensureOnce(): Promise<Ready> {
	booting ??= ensureEnvironment().finally(() => {
		booting = undefined;
	});
	return booting;
}

function appendDoc(): string {
	let raw = "";
	try {
		raw = fs.readFileSync(APPEND_FILE, "utf8");
	} catch {
		return "";
	}
	return raw
		.replace(/\r\n/g, "\n")
		.split("\n")
		.filter((line) => !/^<!--\s*podcast-kg:(start|end)\s*-->$/.test(line.trim()))
		.join("\n")
		.trim();
}

export default function podcastKnowledgeGraph(pi: ExtensionAPI) {
	// Kick the environment off with the process, but do not block extension load:
	// Pi also loads extensions for invocations that never start a session.
	// Never let a boot failure reject: an unhandled rejection here kills Pi at
	// extension load (EBUSY on a locked shim used to do exactly that).
	const bootPromise: Promise<Ready> = ensureOnce().catch((error: unknown) => ({
		ok: false,
		note: `环境准备异常：${error instanceof Error ? error.message : String(error)}。可运行 /podcast-kg 或 podcast-kg doctor 复查。`,
	}));

	pi.on("session_start", async (_event, ctx) => {
		const state = await bootPromise;
		if (state.ok) {
			prependToPath(BIN_DIR);
			ctx.ui.notify(`podcast-kg 就绪${state.python ? `（${state.python}）` : ""}`, "info");
		} else {
			ctx.ui.notify(`podcast-kg 不可用：${state.note}`, "error");
		}
	});

	pi.on("resources_discover", async () => {
		if (fs.existsSync(path.join(SKILLS_DIR, "podcast-knowledge-graph", "SKILL.md"))) {
			return { skillPaths: [SKILLS_DIR] };
		}
		return undefined;
	});

	pi.on("before_agent_start", async (event) => {
		const doc = appendDoc();
		if (!doc) return;
		const options = event.systemPromptOptions;
		const current = options.appendSystemPrompt ?? "";
		if (current.includes("podcast-kg --help")) return;
		const state = ready;
		const status = state ? `\n\n运行时：${state.note}` : "";
		options.appendSystemPrompt = `${current}${current ? "\n\n" : ""}${doc}${status}\n`;
	});

	pi.registerCommand("podcast-kg", {
		description: "检查 podcast-kg 环境（等同 podcast-kg doctor）",
		handler: async (args, ctx) => {
			const state = await ensureOnce();
			if (!state.ok || !state.cli) {
				ctx.ui.notify(state.note, "error");
				return;
			}
			const extra = args.trim() ? args.trim().split(/\s+/) : ["doctor"];
			const child = spawn(state.cli, extra, { windowsHide: true });
			let out = "";
			child.stdout.on("data", (chunk) => (out += chunk.toString()));
			child.stderr.on("data", (chunk) => (out += chunk.toString()));
			await new Promise<void>((resolve) => child.on("close", () => resolve()));
			ctx.ui.notify(out.trim() || "（无输出）", "info");
		},
	});
}
