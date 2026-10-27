import assert from "node:assert/strict";
import { collectSubscription, hasOpenDesignSession, subscriptionCredentialRefs } from "../lib/subscriptions.js";

function credentials(values) {
	return {
		resolve: async (ref) => Object.hasOwn(values, ref) ? { value: values[ref] } : void 0
	};
}

const noLocalConfig = {
	homedir: () => "/test-home",
	readFile: async () => { throw new Error("missing"); }
};

const PREFLIGHT = {
	schemaVersion: 1,
	workspaceId: "ws_test",
	workspaceMemberId: "wm_test",
	modelId: null,
	generatedAt: "2026-10-22T02:38:04.908Z",
	balanceUsd: "1.0000",
	codingPlan: {
		workspaceId: "ws_test",
		generatedAt: "2026-10-22T02:38:04.904Z",
		eligible: true,
		tier: "go",
		windows: [
			{
				policyId: "policy_5h",
				durationSeconds: 18000,
				resetMode: "anchored_recurring",
				usedCredits: "1197",
				limitCredits: "50000",
				remainingCredits: "48803",
				windowStart: "2026-10-21T22:03:12.000Z",
				resetsAt: "2026-10-22T03:03:12.000Z"
			},
			{
				policyId: "policy_7d",
				durationSeconds: 604800,
				resetMode: "anchored_recurring",
				usedCredits: "1437",
				limitCredits: "150000",
				remainingCredits: "148563",
				windowStart: "2026-10-21T02:03:12.000Z",
				resetsAt: "2026-10-28T02:03:12.000Z"
			}
		]
	},
	modelCovered: null,
	funding: "wallet"
};

// ——— no credential anywhere → not-configured, no network ———
{
	const calls = [];
	const provider = await collectSubscription("opendesign", credentials({}), {}, {
		...noLocalConfig,
		fetch: async (url) => { calls.push(String(url)); throw new Error("must not fetch"); }
	});
	assert.equal(provider.status, "not-configured");
	assert.deepEqual(provider.windows, []);
	assert.deepEqual(provider.missingCredentials, [subscriptionCredentialRefs.openDesignControlKey]);
	assert.equal(calls.length, 0, "no request may be made without a session");
	assert.equal(await hasOpenDesignSession(credentials({}), noLocalConfig), false);
	console.log("OpenDesign not-configured state ok");
}

// ——— explicit control key: workspace discovery then preflight, Go 5h + 7d ———
{
	const calls = [];
	const secret = "ctrl-key-for-tests";
	const provider = await collectSubscription("opendesign", credentials({
		[subscriptionCredentialRefs.openDesignControlKey]: secret
	}), {}, {
		...noLocalConfig,
		now: () => Date.parse("2026-10-22T02:40:00Z"),
		fetch: async (url, init) => {
			calls.push({ url: String(url), auth: init?.headers?.authorization });
			if (String(url).endsWith("/api/v1/workspaces")) {
				return { ok: true, status: 200, json: async () => ({ items: [
					{ workspaceId: "ws_test", workspaceType: "personal" }
				] }) };
			}
			return { ok: true, status: 200, json: async () => PREFLIGHT };
		}
	});
	assert.equal(provider.status, "ok");
	assert.equal(provider.plan, "OpenDesign Go");
	assert.equal(provider.mode, "subscription");
	assert.equal(calls.length, 2);
	assert.equal(calls[0].url, "https://amr-api.open-design.ai/api/v1/workspaces");
	assert.equal(
		calls[1].url,
		"https://amr-api.open-design.ai/api/v1/workspaces/ws_test/billing/preflight"
	);
	assert.equal(calls[1].auth, `Bearer ${secret}`);
	assert.equal(JSON.stringify(provider).includes(secret), false, "control key must not cross the module interface");

	const [fiveHour, sevenDay] = provider.windows;
	assert.equal(fiveHour.kind, "session");
	assert.deepEqual(fiveHour.period, { unit: "hours", count: 5 });
	assert.equal(fiveHour.usedPercent, 2.4);
	assert.equal(fiveHour.remainingPercent, 97.6);
	assert.equal(fiveHour.resetsAt, "2026-10-22T03:03:12.000Z");
	assert.equal(fiveHour.policyId, "policy_5h");
	assert.equal(fiveHour.durationSeconds, 18000);

	assert.equal(sevenDay.kind, "weekly");
	assert.deepEqual(sevenDay.period, { unit: "days", count: 7 });
	assert.equal(sevenDay.usedPercent, 1);
	assert.equal(sevenDay.remainingPercent, 99);
	assert.equal(sevenDay.resetsAt, "2026-10-28T02:03:12.000Z");

	// The wallet behind the plan stays a balance, like Command Code's credits.
	assert.equal(provider.credits.remaining, 1);
	assert.equal(provider.credits.currency, "USD");
	console.log("OpenDesign Go 5h + 7d windows ok");
}

// ——— an explicit workspace id skips the directory call ———
{
	const calls = [];
	const provider = await collectSubscription("opendesign", credentials({
		[subscriptionCredentialRefs.openDesignControlKey]: "ctrl",
		[subscriptionCredentialRefs.openDesignWorkspaceId]: "ws_direct"
	}), {}, {
		...noLocalConfig,
		fetch: async (url) => {
			calls.push(String(url));
			return { ok: true, status: 200, json: async () => PREFLIGHT };
		}
	});
	assert.equal(provider.status, "ok");
	assert.equal(calls.length, 1);
	assert.equal(calls[0], "https://amr-api.open-design.ai/api/v1/workspaces/ws_direct/billing/preflight");
	console.log("OpenDesign explicit workspace id ok");
}

// ——— control key from the Open Design client's own ~/.amr/config.json ———
{
	const files = [];
	const provider = await collectSubscription("opendesign", credentials({}), {}, {
		homedir: () => "/home/tester",
		readFile: async (path) => {
			files.push(path);
			return JSON.stringify({
				profiles: {
					prod: {
						controlKey: "file-ctrl",
						apiUrl: "https://amr-api.open-design.ai",
						user: { id: "u1", email: "tester@example.com" }
					}
				}
			});
		},
		fetch: async (url) => {
			if (String(url).endsWith("/api/v1/workspaces")) {
				return { ok: true, status: 200, json: async () => ({ items: [{ workspaceId: "ws_file", workspaceType: "personal" }] }) };
			}
			return { ok: true, status: 200, json: async () => PREFLIGHT };
		}
	});
	// `join()` is platform-specific, so compare on the separator-normalized form.
	assert.equal(files[0].replaceAll("\\", "/"), "/home/tester/.amr/config.json");
	assert.equal(provider.status, "ok");
	assert.equal(provider.plan, "OpenDesign Go");
	assert.equal(await hasOpenDesignSession(credentials({}), {
		homedir: () => "/home/tester",
		readFile: async () => JSON.stringify({ profiles: { prod: { controlKey: "x" } } })
	}), true);
	console.log("OpenDesign ~/.amr/config.json session ok");
}

// ——— a paid tier with only a 7-day pool still renders ———
{
	const provider = await collectSubscription("opendesign", credentials({
		[subscriptionCredentialRefs.openDesignControlKey]: "ctrl",
		[subscriptionCredentialRefs.openDesignWorkspaceId]: "ws"
	}), {}, {
		...noLocalConfig,
		fetch: async () => ({
			ok: true,
			status: 200,
			json: async () => ({
				...PREFLIGHT,
				codingPlan: {
					...PREFLIGHT.codingPlan,
					tier: "pro",
					windows: [PREFLIGHT.codingPlan.windows[1]]
				}
			})
		})
	});
	assert.equal(provider.status, "ok");
	assert.equal(provider.plan, "OpenDesign Pro");
	assert.equal(provider.windows.length, 1);
	assert.equal(provider.windows[0].kind, "weekly");
	console.log("OpenDesign paid-tier single 7-day window ok");
}

// ——— a broken window is dropped without taking the readable one down ———
{
	const provider = await collectSubscription("opendesign", credentials({
		[subscriptionCredentialRefs.openDesignControlKey]: "ctrl",
		[subscriptionCredentialRefs.openDesignWorkspaceId]: "ws"
	}), {}, {
		...noLocalConfig,
		fetch: async () => ({
			ok: true,
			status: 200,
			json: async () => ({
				...PREFLIGHT,
				codingPlan: {
					...PREFLIGHT.codingPlan,
					windows: [
						{ ...PREFLIGHT.codingPlan.windows[0], limitCredits: "0" },
						PREFLIGHT.codingPlan.windows[1]
					]
				}
			})
		})
	});
	assert.equal(provider.status, "ok");
	assert.equal(provider.windows.length, 1);
	assert.equal(provider.windows[0].kind, "weekly");
	console.log("OpenDesign unreadable window isolation ok");
}

// ——— upstream rejection maps to unauthorized, never to a fake 0% ———
{
	const provider = await collectSubscription("opendesign", credentials({
		[subscriptionCredentialRefs.openDesignControlKey]: "bad",
		[subscriptionCredentialRefs.openDesignWorkspaceId]: "ws"
	}), {}, {
		...noLocalConfig,
		fetch: async () => ({ ok: false, status: 401, json: async () => ({ error: "unauthenticated" }) })
	});
	assert.equal(provider.status, "unauthorized");
	assert.deepEqual(provider.windows, []);
	console.log("OpenDesign unauthorized mapping ok");
}

console.log("OPEN DESIGN SUBSCRIPTION TESTS PASSED");
