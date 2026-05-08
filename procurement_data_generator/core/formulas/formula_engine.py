"""Safe structured formula execution for generated procurement DataFrames."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

import numpy as np
import pandas as pd

from procurement_data_generator.core.contracts.llm_plan_contract import FormulaRule, LLMGenerationPlan
from procurement_data_generator.core.contracts.schema_contract import ColumnContract, SchemaContract


EXECUTABLE_OPERATIONS = {
    "add",
    "subtract",
    "multiply",
    "divide",
    "sum",
    "count",
    "avg",
    "min",
    "max",
    "date_diff",
    "percentage",
}
VALIDATION_ONLY_OPERATIONS = {"equals", "less_than_or_equal", "greater_than_or_equal"}


@dataclass
class FormulaRuleExecutionResult:
    """Execution status for one formula rule."""

    rule_id: str
    rule_type: str
    target_table: str
    target_column: str
    operation: str
    status: str
    message: str
    rows_affected: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def error_count(self) -> int:
        return len(self.errors)


@dataclass
class FormulaExecutionReport:
    """Summary report for a formula execution run."""

    total_rules: int = 0
    results: list[FormulaRuleExecutionResult] = field(default_factory=list)

    @property
    def applied_rules(self) -> list[FormulaRuleExecutionResult]:
        return [result for result in self.results if result.status == "applied"]

    @property
    def skipped_rules(self) -> list[FormulaRuleExecutionResult]:
        return [result for result in self.results if result.status == "skipped"]

    @property
    def failed_rules(self) -> list[FormulaRuleExecutionResult]:
        return [result for result in self.results if result.status == "failed"]

    @property
    def applied_count(self) -> int:
        return len(self.applied_rules)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_rules)

    @property
    def failed_count(self) -> int:
        return len(self.failed_rules)

    @property
    def warning_count(self) -> int:
        return sum(result.warning_count for result in self.results)

    @property
    def error_count(self) -> int:
        return sum(result.error_count for result in self.results)

    @property
    def status(self) -> str:
        if self.failed_count:
            return "failed"
        if self.warning_count or self.skipped_count:
            return "passed_with_warnings"
        return "passed"


class SafeFormulaEngine:
    """Execute validated formula rules without eval or arbitrary code execution."""

    def execute_formulas(
        self,
        dataframes: dict[str, pd.DataFrame],
        plan: LLMGenerationPlan,
        schema: SchemaContract | None = None,
        strict: bool = False,
    ) -> tuple[dict[str, pd.DataFrame], FormulaExecutionReport]:
        """Apply structured FormulaRule objects to copies of the input DataFrames."""

        updated = {table_name: dataframe.copy(deep=True) for table_name, dataframe in dataframes.items()}
        report = FormulaExecutionReport(total_rules=len(plan.formula_rules))

        for rule in self._ordered_formula_rules(plan.formula_rules):
            result = self._execute_rule(updated, rule, schema)
            report.results.append(result)
            if strict and result.status == "failed":
                break

        return updated, report

    def _execute_rule(
        self,
        dataframes: dict[str, pd.DataFrame],
        rule: FormulaRule,
        schema: SchemaContract | None,
    ) -> FormulaRuleExecutionResult:
        if rule.operation in VALIDATION_ONLY_OPERATIONS:
            return self._skipped(rule, f"Operation {rule.operation!r} is validation-only and is not executed in Phase 10.")
        if rule.operation not in EXECUTABLE_OPERATIONS:
            return self._failed(rule, f"Unsupported formula operation: {rule.operation}.")
        if rule.target_table not in dataframes:
            return self._failed(rule, f"Target table {rule.target_table} was not found.")
        if rule.target_column not in dataframes[rule.target_table].columns:
            return self._failed(rule, f"Target column {rule.target_table}.{rule.target_column} was not found.")

        try:
            if rule.rule_type == "row_level":
                rows = self._apply_row_level(dataframes, rule, schema)
            elif rule.rule_type == "aggregate":
                rows = self._apply_aggregate(dataframes, rule, schema)
            elif rule.rule_type == "date_diff":
                rows = self._apply_date_diff(dataframes, rule, schema)
            elif rule.rule_type == "percentage":
                rows = self._apply_percentage(dataframes, rule, schema)
            elif rule.rule_type == "quantity_reconciliation":
                rows = self._apply_quantity_reconciliation(dataframes, rule, schema)
            elif rule.rule_type == "inventory_balance":
                rows = self._apply_inventory_balance(dataframes, rule, schema)
            else:
                return self._failed(rule, f"Unsupported formula rule_type: {rule.rule_type}.")
        except FormulaExecutionError as exc:
            return self._failed(rule, str(exc))

        warnings = self._post_apply_warnings(dataframes, rule, schema)
        return FormulaRuleExecutionResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            target_table=rule.target_table,
            target_column=rule.target_column,
            operation=rule.operation,
            status="applied",
            rows_affected=rows,
            message="Formula rule applied successfully.",
            warnings=warnings,
        )

    def _apply_row_level(self, dataframes: dict[str, pd.DataFrame], rule: FormulaRule, schema: SchemaContract | None) -> int:
        dataframe = dataframes[rule.target_table]
        if rule.operation not in {"add", "subtract", "multiply", "divide"}:
            raise FormulaExecutionError(f"Row-level rule {rule.rule_id} does not support operation {rule.operation}.")
        self._require_columns(dataframe, rule.input_columns, rule.target_table)
        if len(rule.input_columns) < 2:
            raise FormulaExecutionError("Row-level formulas require at least two input_columns.")

        column = self._schema_column(schema, rule.target_table, rule.target_column)
        decimals = self._decimal_scale(column, rule.target_column)
        if rule.operation == "multiply" and decimals is not None:
            result = self._row_decimal_multiply(dataframe, rule.input_columns, decimals)
        else:
            result = self._row_operation(dataframe, rule.input_columns, rule.operation)
        dataframe[rule.target_column] = self._coerce_result(result, rule, schema)
        return len(dataframe)

    def _apply_aggregate(self, dataframes: dict[str, pd.DataFrame], rule: FormulaRule, schema: SchemaContract | None) -> int:
        if rule.operation not in {"sum", "count", "avg", "min", "max"}:
            raise FormulaExecutionError(f"Aggregate rule {rule.rule_id} does not support operation {rule.operation}.")
        if not rule.source_table or rule.source_table not in dataframes:
            raise FormulaExecutionError(f"Source table {rule.source_table!r} was not found.")
        if not rule.relationship_key and not rule.group_by_columns:
            raise FormulaExecutionError("Aggregate formulas require relationship_key or group_by_columns.")

        target = dataframes[rule.target_table]
        source = dataframes[rule.source_table]
        if rule.group_by_columns and not rule.relationship_key:
            return self._apply_grouped_aggregate(dataframes, rule, schema)

        self._require_columns(target, [rule.relationship_key, rule.target_column], rule.target_table)
        self._require_columns(source, [rule.relationship_key], rule.source_table)
        if rule.operation != "count":
            if not rule.source_column:
                raise FormulaExecutionError("Aggregate formulas require source_column for sum/avg/min/max.")
            self._require_columns(source, [rule.source_column], rule.source_table)
            series = pd.to_numeric(source[rule.source_column], errors="coerce")
            grouped = getattr(series.groupby(source[rule.relationship_key]), self._pandas_agg_name(rule.operation))()
        else:
            count_column = rule.source_column if rule.source_column in source.columns else rule.relationship_key
            grouped = source.groupby(rule.relationship_key)[count_column].count()

        mapped = target[rule.relationship_key].map(grouped)
        if rule.operation == "count":
            mapped = mapped.fillna(0).astype(int)
        target[rule.target_column] = self._coerce_result(mapped, rule, schema)
        return int(mapped.notna().sum())

    def _apply_grouped_aggregate(self, dataframes: dict[str, pd.DataFrame], rule: FormulaRule, schema: SchemaContract | None) -> int:
        if not rule.source_table or rule.source_table not in dataframes:
            raise FormulaExecutionError(f"Source table {rule.source_table!r} was not found.")
        if not rule.group_by_columns:
            raise FormulaExecutionError("Grouped aggregate formulas require group_by_columns.")

        target = dataframes[rule.target_table]
        source = dataframes[rule.source_table]
        self._require_columns(target, [*rule.group_by_columns, rule.target_column], rule.target_table)
        self._require_columns(source, rule.group_by_columns, rule.source_table)

        if rule.operation != "count":
            if not rule.source_column:
                raise FormulaExecutionError("Aggregate formulas require source_column for sum/avg/min/max.")
            self._require_columns(source, [rule.source_column], rule.source_table)
            grouped_source = source.copy()
            grouped_source["__formula_source"] = pd.to_numeric(grouped_source[rule.source_column], errors="coerce")
            grouped = (
                grouped_source.groupby(rule.group_by_columns, dropna=False)["__formula_source"]
                .agg(self._pandas_agg_name(rule.operation))
                .reset_index()
                .rename(columns={"__formula_source": "__formula_value"})
            )
        else:
            count_column = rule.source_column if rule.source_column in source.columns else rule.group_by_columns[0]
            grouped = (
                source.groupby(rule.group_by_columns, dropna=False)[count_column]
                .count()
                .reset_index()
                .rename(columns={count_column: "__formula_value"})
            )

        merged = target[rule.group_by_columns].merge(grouped, on=rule.group_by_columns, how="left")
        values = merged["__formula_value"]
        if rule.operation == "count":
            values = values.fillna(0).astype(int)
        target[rule.target_column] = self._coerce_result(values, rule, schema)
        return int(values.notna().sum())

    def _apply_date_diff(self, dataframes: dict[str, pd.DataFrame], rule: FormulaRule, schema: SchemaContract | None) -> int:
        dataframe = dataframes[rule.target_table]
        if rule.operation != "date_diff":
            raise FormulaExecutionError("date_diff rule_type requires date_diff operation.")
        if len(rule.input_columns) != 2:
            raise FormulaExecutionError("date_diff formulas require exactly two input_columns.")
        self._require_columns(dataframe, rule.input_columns, rule.target_table)
        later = pd.to_datetime(dataframe[rule.input_columns[0]], errors="coerce")
        earlier = pd.to_datetime(dataframe[rule.input_columns[1]], errors="coerce")
        result = (later - earlier).dt.days.astype("Float64")
        dataframe[rule.target_column] = self._coerce_result(result, rule, schema)
        return int(result.notna().sum())

    def _apply_percentage(self, dataframes: dict[str, pd.DataFrame], rule: FormulaRule, schema: SchemaContract | None) -> int:
        dataframe = dataframes[rule.target_table]
        if rule.operation not in {"percentage", "divide"}:
            raise FormulaExecutionError("percentage rule_type requires percentage or divide operation.")
        denominator_column = rule.denominator_column or (rule.input_columns[1] if len(rule.input_columns) > 1 else None)
        if not rule.input_columns or not denominator_column:
            raise FormulaExecutionError("Percentage formulas require numerator and denominator columns.")
        self._require_columns(dataframe, [rule.input_columns[0], denominator_column], rule.target_table)
        numerator = pd.to_numeric(dataframe[rule.input_columns[0]], errors="coerce")
        denominator = pd.to_numeric(dataframe[denominator_column], errors="coerce")
        result = self._safe_divide(numerator, denominator) * 100
        dataframe[rule.target_column] = self._coerce_result(result.round(2), rule, schema)
        return int(result.notna().sum())

    def _apply_quantity_reconciliation(
        self,
        dataframes: dict[str, pd.DataFrame],
        rule: FormulaRule,
        schema: SchemaContract | None,
    ) -> int:
        if rule.operation in VALIDATION_ONLY_OPERATIONS:
            raise FormulaExecutionError(f"Quantity comparison operation {rule.operation} belongs to Phase 11 validation.")
        if rule.source_table and rule.relationship_key and rule.operation == "sum":
            return self._apply_aggregate(dataframes, rule, schema)
        return self._apply_row_level(dataframes, rule, schema)

    def _apply_inventory_balance(
        self,
        dataframes: dict[str, pd.DataFrame],
        rule: FormulaRule,
        schema: SchemaContract | None,
    ) -> int:
        if rule.operation != "sum":
            raise FormulaExecutionError("inventory_balance formulas currently support sum only.")
        if not rule.source_table or rule.source_table not in dataframes:
            raise FormulaExecutionError(f"Source table {rule.source_table!r} was not found.")
        if not rule.source_column:
            raise FormulaExecutionError("inventory_balance formulas require source_column.")
        if not rule.group_by_columns:
            raise FormulaExecutionError("inventory_balance formulas require group_by_columns.")

        target = dataframes[rule.target_table]
        source = dataframes[rule.source_table]
        self._require_columns(target, [*rule.group_by_columns, rule.target_column], rule.target_table)
        self._require_columns(source, [*rule.group_by_columns, rule.source_column], rule.source_table)

        grouped = (
            source.groupby(rule.group_by_columns, dropna=False)[rule.source_column]
            .sum()
            .reset_index()
            .rename(columns={rule.source_column: "__formula_value"})
        )
        merged = target[rule.group_by_columns].merge(grouped, on=rule.group_by_columns, how="left")
        target[rule.target_column] = self._coerce_result(merged["__formula_value"], rule, schema)
        return int(merged["__formula_value"].notna().sum())

    def _binary_operation(self, left: pd.Series, right: pd.Series, operation: str) -> pd.Series:
        left_num = pd.to_numeric(left, errors="coerce")
        right_num = pd.to_numeric(right, errors="coerce")
        if operation == "add":
            return left_num + right_num
        if operation == "subtract":
            return left_num - right_num
        if operation == "multiply":
            return left_num * right_num
        if operation == "divide":
            return self._safe_divide(left_num, right_num)
        raise FormulaExecutionError(f"Unsupported binary operation: {operation}.")

    def _row_operation(self, dataframe: pd.DataFrame, input_columns: list[str], operation: str) -> pd.Series:
        values = [pd.to_numeric(dataframe[column], errors="coerce") for column in input_columns]
        result = values[0]
        if operation == "add":
            for value in values[1:]:
                result = result + value
            return result
        if operation == "subtract":
            for value in values[1:]:
                result = result - value
            return result
        if operation == "multiply":
            for value in values[1:]:
                result = result * value
            return result
        if operation == "divide":
            for value in values[1:]:
                result = self._safe_divide(result, value)
            return result
        raise FormulaExecutionError(f"Unsupported row-level operation: {operation}.")

    def _row_decimal_multiply(self, dataframe: pd.DataFrame, input_columns: list[str], decimals: int) -> pd.Series:
        quantizer = Decimal("1").scaleb(-decimals)

        def multiply_row(row: pd.Series) -> float | pd.NA:
            value = Decimal("1")
            for column_name in input_columns:
                raw_value = row[column_name]
                if pd.isna(raw_value):
                    return pd.NA
                value *= Decimal(str(raw_value))
            return float(value.quantize(quantizer, rounding=ROUND_HALF_EVEN))

        return dataframe[input_columns].apply(multiply_row, axis=1)

    def _ordered_formula_rules(self, rules: list[FormulaRule]) -> list[FormulaRule]:
        """Order formulas so row-level dependencies are available before aggregate/percentage rules."""

        target_by_table_column = {(rule.target_table, rule.target_column): rule for rule in rules}

        def priority(rule: FormulaRule) -> tuple[int, int]:
            if rule.rule_type == "percentage":
                dependency_bonus = 5 if any((rule.target_table, column) in target_by_table_column for column in rule.input_columns) else 0
                return (40 + dependency_bonus, 0)
            if rule.rule_type == "aggregate":
                source_dependency_bonus = 5 if rule.source_table and (rule.source_table, rule.source_column or "") in target_by_table_column else 0
                return (60 + source_dependency_bonus, 0)
            if rule.rule_type == "inventory_balance":
                return (70, 0)
            if rule.rule_type == "quantity_reconciliation":
                return (20, 0)
            if rule.rule_type == "date_diff":
                return (30, 0)
            if rule.rule_type == "row_level":
                return (10, 0)
            return (50, 0)

        return sorted(rules, key=priority)

    def _safe_divide(self, numerator: pd.Series, denominator: pd.Series) -> pd.Series:
        result = numerator / denominator.replace({0: pd.NA})
        return self._clean_invalid_numbers(result)

    def _coerce_result(self, result: pd.Series, rule: FormulaRule, schema: SchemaContract | None) -> pd.Series:
        clean = self._clean_invalid_numbers(result)
        column = self._schema_column(schema, rule.target_table, rule.target_column)
        decimals = self._decimal_scale(column, rule.target_column)
        if decimals is not None:
            clean = pd.to_numeric(clean, errors="coerce").round(decimals).astype("Float64")
        if column is not None and self._is_integer_type(column.data_type):
            numeric = pd.to_numeric(clean, errors="coerce")
            if numeric.dropna().mod(1).eq(0).all():
                return numeric.astype("Int64")
        return clean

    def _post_apply_warnings(
        self,
        dataframes: dict[str, pd.DataFrame],
        rule: FormulaRule,
        schema: SchemaContract | None,
    ) -> list[str]:
        warnings: list[str] = []
        series = dataframes[rule.target_table][rule.target_column]
        if self._contains_infinity(series):
            warnings.append("Target column still contains infinity values after cleanup.")
        column = self._schema_column(schema, rule.target_table, rule.target_column)
        if column is not None and column.nullable == "No" and series.isna().any():
            warnings.append(f"Non-nullable target column {rule.target_table}.{rule.target_column} contains null formula results.")
        return warnings

    def _require_columns(self, dataframe: pd.DataFrame, columns: list[str], table_name: str) -> None:
        missing = [column for column in columns if column not in dataframe.columns]
        if missing:
            raise FormulaExecutionError(f"Missing required column(s) in {table_name}: {', '.join(missing)}.")

    def _clean_invalid_numbers(self, series: pd.Series) -> pd.Series:
        return pd.Series(series).replace([np.inf, -np.inf], pd.NA)

    def _contains_infinity(self, series: pd.Series) -> bool:
        numeric = pd.to_numeric(series, errors="coerce")
        return bool(np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any())

    def _pandas_agg_name(self, operation: str) -> str:
        return {"avg": "mean"}.get(operation, operation)

    def _schema_column(self, schema: SchemaContract | None, table_name: str, column_name: str) -> ColumnContract | None:
        if schema is None or table_name not in schema.tables:
            return None
        for column in schema.tables[table_name].columns:
            if column.column_name == column_name:
                return column
        return None

    def _decimal_scale(self, column: ColumnContract | None, column_name: str) -> int | None:
        if "amount" in column_name.lower() or "price" in column_name.lower() or "rate" in column_name.lower() or "pct" in column_name.lower():
            return 2
        if column is None:
            return None
        data_type = column.data_type.lower()
        if "decimal" in data_type or "numeric" in data_type:
            if "," in data_type and ")" in data_type:
                try:
                    return int(data_type.split(",", 1)[1].split(")", 1)[0].strip())
                except ValueError:
                    return 2
            return 2
        return None

    def _is_integer_type(self, data_type: str) -> bool:
        lowered = data_type.lower()
        return any(token in lowered for token in ("int", "bigint", "smallint")) and "decimal" not in lowered

    def _failed(self, rule: FormulaRule, message: str) -> FormulaRuleExecutionResult:
        return FormulaRuleExecutionResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            target_table=rule.target_table,
            target_column=rule.target_column,
            operation=rule.operation,
            status="failed",
            message=message,
            errors=[message],
        )

    def _skipped(self, rule: FormulaRule, message: str) -> FormulaRuleExecutionResult:
        return FormulaRuleExecutionResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            target_table=rule.target_table,
            target_column=rule.target_column,
            operation=rule.operation,
            status="skipped",
            message=message,
            warnings=[message],
        )


class FormulaExecutionError(Exception):
    """Raised for one safely handled formula rule failure."""


def format_formula_execution_report(
    report: FormulaExecutionReport,
    output_folder: str | None = None,
    model_version: str | None = None,
) -> str:
    """Format formula execution results for CLI output."""

    lines = [
        "Formula execution completed.",
    ]
    if model_version is not None:
        lines.append(f"Model version: {model_version}")
    lines.extend(
        [
            f"Total rules: {report.total_rules}",
            f"Applied rules: {report.applied_count}",
            f"Skipped rules: {report.skipped_count}",
            f"Failed rules: {report.failed_count}",
            f"Warnings: {report.warning_count}",
            f"Errors: {report.error_count}",
        ]
    )
    if output_folder:
        lines.append(f"Output folder: {output_folder}")
    lines.append(f"Formula status: {report.status}")

    details = [result for result in report.results if result.status != "applied" or result.warnings]
    if details:
        lines.append("")
        lines.append("Rule details:")
        for index, result in enumerate(details, start=1):
            lines.append(f"{index}. Rule: {result.rule_id}")
            lines.append(f"   Status: {result.status}")
            lines.append(f"   Message: {result.message}")
    return "\n".join(lines)
