import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

/**
 * Ringkasan migrasi: status batch terakhir per entitas dan hasil
 * rekonsiliasi terakhir per jenis. Datanya dari
 * jembatan.reconcile.run.get_dashboard_data.
 */
export class MigrationDashboard extends Component {
    static template = "jembatan_reconcile.MigrationDashboard";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("jembatan.reconcile.run", "get_dashboard_data", []);
    }

    formatAmount(value) {
        return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value);
    }

    batchClass(batch) {
        return {
            done: "text-bg-success",
            partial: "text-bg-warning",
            failed: "text-bg-danger",
        }[batch.state] || "text-bg-secondary";
    }

    openRun() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "jembatan.reconcile.run",
            res_id: this.state.data.run.id,
            views: [[false, "form"]],
        });
    }

    openBatches() {
        this.action.doAction("jembatan_migration.action_migration_batch");
    }

    async newRun() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Rekonsiliasi baru"),
            res_model: "jembatan.reconcile.run",
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("jembatan_reconcile.dashboard", MigrationDashboard);
