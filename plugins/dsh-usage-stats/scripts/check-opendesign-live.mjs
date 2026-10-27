// Live end-to-end check: read the real Open Design session and print the
// normalized account snapshot the panel would render. Prints no secrets.
import { collectSubscription, hasOpenDesignSession } from "../lib/subscriptions.js";

const credentials = { resolve: async () => void 0 };

const available = await hasOpenDesignSession(credentials, {});
console.log(`hasOpenDesignSession: ${available}`);

const provider = await collectSubscription("opendesign", credentials, {}, {});
console.log(`status: ${provider.status}`);
console.log(`plan:   ${provider.plan ?? "(none)"}`);
if (provider.credits) console.log(`wallet: ${provider.credits.remaining} ${provider.credits.currency}`);
for (const window of provider.windows) {
	const period = window.period ? `${window.period.count} ${window.period.unit}` : window.kind;
	console.log(
		`  ${period.padEnd(12)} used ${String(window.usedPercent).padStart(5)}%  ` +
		`remaining ${String(window.remainingPercent).padStart(5)}%  ` +
		`resets ${window.resetsAt ?? "-"}`
	);
}
if (provider.status !== "ok") process.exitCode = 1;
