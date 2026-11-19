import json
import logging
import sys
import xml.etree.ElementTree as ET

from collections.abc import Mapping
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path

import pandas as pd


logger = logging.getLogger(__name__)


# ============================================================
# KONFIGURATION
# Alle Dateien liegen im selben Ordner wie diese app.py.
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

SOURCE_FILE = BASE_DIR / 'Kopie.csv'
CLEAN_FILE = BASE_DIR / 'clean.csv'

MATCHED_FILE = BASE_DIR / 'matched.csv'
UNMATCHED_FILE = BASE_DIR / 'unmatched.csv'
SAP_FILE = BASE_DIR / 'SAP-Output.csv'

COLUMNS_FILE = BASE_DIR / 'columns.json'

XML_TEMPLATE_FILE = BASE_DIR / 'xml_template.xml'
XML_MAPPING_FILE = BASE_DIR / 'xml_mapping.json'

# Einzelne XML-Dateien direkt neben app.py speichern.
EXPORT_DIR = BASE_DIR

# An das tatsächliche Format deiner Dateien anpassen.
CSV_SEPARATOR = ','
CSV_ENCODING = 'utf-8'

SHORT_TEXT_COLUMN = 'Kurztext'
TECHNICAL_PLACE_COLUMN = 'Technischer Platz'
SAP_SHORT_TEXT_COLUMN = 'SAP Kurztext'

# Zuordnung: SAP-Zielspalte -> Quellspalte im bestätigten Eintrag.
#
# Gleichnamige weitere Spalten werden ebenfalls übernommen.
# Zusätzliche abweichende Spaltennamen hier ergänzen.
SAP_LEARNING_MAPPING = {
    SAP_SHORT_TEXT_COLUMN: SHORT_TEXT_COLUMN,
}


# ============================================================
# ALLGEMEINE DATEI- UND VALIDIERUNGSFUNKTIONEN
# ============================================================

def _read_csv(file_path):
    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(
            f'Die erforderliche CSV-Datei fehlt: {file_path}'
        )

    return pd.read_csv(
        file_path,
        sep=CSV_SEPARATOR,
        encoding=CSV_ENCODING,
        dtype=str,
        keep_default_na=False
    )


def _write_csv_atomic(df, file_path):
    """
    Schreibt zunächst eine temporäre Datei und ersetzt
    anschließend die Zieldatei.

    Das schützt die einzelne Datei, ist aber keine Transaktion
    über mehrere CSV- und XML-Dateien.
    """
    file_path = Path(file_path)
    temp_file = file_path.with_suffix(file_path.suffix + '.tmp')

    try:
        df.to_csv(
            temp_file,
            sep=CSV_SEPARATOR,
            encoding=CSV_ENCODING,
            index=False
        )

        temp_file.replace(file_path)

    finally:
        if temp_file.exists():
            temp_file.unlink()


def _require_columns(df, required_columns, description):
    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f'{description}: Folgende Spalten fehlen: '
            + ', '.join(missing)
        )


def _normalized_short_text(series):
    return series.astype(str).str.strip().str.upper()


def _load_columns():
    with COLUMNS_FILE.open(encoding='utf-8') as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise ValueError(
            'columns.json muss ein JSON-Objekt enthalten.'
        )

    columns = config.get('columns')

    if not isinstance(columns, list) or not columns:
        raise ValueError(
            'columns.json benötigt eine nicht leere Liste "columns".'
        )

    normalized_columns = []

    for column in columns:
        if not isinstance(column, dict):
            raise ValueError(
                'Jeder Spalteneintrag muss ein JSON-Objekt sein.'
            )

        field = column.get('field')

        if not isinstance(field, str) or not field:
            raise ValueError(
                'Jeder Spalteneintrag benötigt ein gültiges "field".'
            )

        normalized_column = dict(column)
        normalized_column['label'] = column.get('label') or field

        normalized_columns.append(normalized_column)

    return normalized_columns


def _validate_display_columns(df, columns):
    _require_columns(
        df,
        [column['field'] for column in columns],
        'Spaltenkonfiguration'
    )


def _validate_index(idx, row_count):
    if isinstance(idx, str):
        if not idx.isascii() or not idx.isdecimal():
            raise ValueError('Ungültiger Zeilenindex.')

        idx = int(idx)

    if type(idx) is not int:
        raise ValueError(
            'Der Zeilenindex muss eine Ganzzahl sein.'
        )

    if not 0 <= idx < row_count:
        raise ValueError(
            'Die ausgewählte Zeile existiert nicht mehr.'
        )

    return idx


def _normalize_selections(selections, row_count):
    """
    Akzeptiert:
    {
        "decision_0": "keep",
        "decision_1": "discard"
    }

    Eine leere PHP-Auswahl darf auch als [] ankommen.
    """
    if selections is None:
        return {}

    if isinstance(selections, list) and not selections:
        return {}

    if not isinstance(selections, Mapping):
        raise ValueError(
            'Die Entscheidungen müssen als Zuordnung '
            'übergeben werden.'
        )

    allowed_names = {
        f'decision_{idx}'
        for idx in range(row_count)
    }

    normalized = {}

    for name, decision in selections.items():
        if name not in allowed_names:
            raise ValueError(
                f'Unbekanntes Entscheidungsfeld: {name}'
            )

        if decision not in ('keep', 'discard'):
            raise ValueError(
                f'Ungültige Entscheidung für {name}.'
            )

        normalized[name] = decision

    return normalized


def _build_review_data(
    df,
    columns,
    selections=None,
    edit_index=None,
    error=None
):
    return {
        'rows': df.to_dict(orient='records'),
        'columns': columns,
        'selections': selections or {},
        'edit_index': edit_index,
        'error': error,
        'row_count': len(df)
    }


# ============================================================
# PIPELINE: ROHDATEN BEREINIGEN
# ============================================================

def process_csv(
    input_file=SOURCE_FILE,
    output_file=CLEAN_FILE
):
    """
    Standardimplementierung:
    - normale CSV mit Kopfzeile einlesen
    - äußere Leerzeichen in Spaltennamen entfernen
    - Pflichtspalten prüfen
    - äußere Leerzeichen in allen Feldwerten entfernen

    WICHTIG:
    Falls deine bisherige process_csv() beispielsweise Zeilen
    entfernt, Rohdaten umformt, Spalten umbenennt oder Kennungen
    speziell bereinigt, übernimm hier deren bisherige Logik.
    """
    df = _read_csv(input_file)

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    if df.columns.duplicated().any():
        raise ValueError(
            'Nach der Bereinigung sind Spaltennamen doppelt vorhanden.'
        )

    _require_columns(
        df,
        [TECHNICAL_PLACE_COLUMN, SHORT_TEXT_COLUMN],
        'Quelldatei'
    )

    for column in df.columns:
        df[column] = df[column].str.strip()

    _write_csv_atomic(df, output_file)

    return len(df)


# ============================================================
# PIPELINE: ORIENTIERUNG
# ============================================================

def orientation(clean_file=CLEAN_FILE):
    """
    Ergänzt den Technischen Platz anhand des Kurztexts.

    Achtung:
    Diese Funktion ist wie im bisherigen Ablauf nicht idempotent.
    Deshalb nur auf eine frisch erzeugte clean.csv anwenden.
    """
    df = _read_csv(clean_file)

    _require_columns(
        df,
        [TECHNICAL_PLACE_COLUMN, SHORT_TEXT_COLUMN],
        'Orientierung'
    )

    left_markers = (' LH ', ' LE ', 'L/H')
    right_markers = (' RH ', ' RE ', 'R/H')

    for idx, row in df.iterrows():
        short_text = row[SHORT_TEXT_COLUMN]

        # Bisherige Ausnahme: literal und case-sensitive.
        if 'LH/RE' in short_text:
            continue

        suffix = None

        if any(marker in short_text for marker in left_markers):
            suffix = '-7111'

        elif any(marker in short_text for marker in right_markers):
            suffix = '-7112'

        if suffix is not None:
            df.at[idx, TECHNICAL_PLACE_COLUMN] = (
                row[TECHNICAL_PLACE_COLUMN] + suffix
            )

    _write_csv_atomic(df, clean_file)


# ============================================================
# PIPELINE: KURZTEXT-MATCHING
# ============================================================

def kurztextsuche(
    clean_file=CLEAN_FILE,
    sap_file=SAP_FILE,
    matched_file=MATCHED_FILE,
    unmatched_file=UNMATCHED_FILE
):
    clean_df = _read_csv(clean_file)
    sap_df = _read_csv(sap_file)

    _require_columns(
        clean_df,
        [SHORT_TEXT_COLUMN],
        'Bereinigte CSV'
    )

    _require_columns(
        sap_df,
        [SAP_SHORT_TEXT_COLUMN],
        'SAP-Datei'
    )

    clean_keys = _normalized_short_text(
        clean_df[SHORT_TEXT_COLUMN]
    )

    sap_keys = _normalized_short_text(
        sap_df[SAP_SHORT_TEXT_COLUMN]
    )

    matched_mask = clean_keys.isin(sap_keys)

    matched_df = clean_df.loc[matched_mask].copy()
    unmatched_df = clean_df.loc[~matched_mask].copy()

    _write_csv_atomic(matched_df, matched_file)
    _write_csv_atomic(unmatched_df, unmatched_file)

    return len(matched_df), len(unmatched_df)


def run_pipeline(
    source=SOURCE_FILE,
    clean=CLEAN_FILE,
    sap=SAP_FILE,
    matched=MATCHED_FILE,
    unmatched=UNMATCHED_FILE
):
    """
    Erzeugt einen neuen Datenlauf.

    Überschreibt die angegebenen Pipeline-Ausgaben.
    Nicht bei jedem Review-Aufruf ausführen.
    """
    process_csv(source, clean)
    orientation(clean)

    return kurztextsuche(
        clean_file=clean,
        sap_file=sap,
        matched_file=matched,
        unmatched_file=unmatched
    )


def initialize_review():
    """
    Initialisiert nur, wenn noch keine Review-Dateien existieren.
    Vorhandener Bearbeitungsfortschritt wird nicht überschrieben.
    """
    if UNMATCHED_FILE.exists():
        if not MATCHED_FILE.exists():
            raise FileNotFoundError(
                'Die Unmatched-Datei ist vorhanden, '
                'aber die zugehörige Matches-Datei fehlt.'
            )

        return {
            'initialized': False,
            'message': (
                'Vorhandene Review-Dateien werden verwendet.'
            )
        }

    if MATCHED_FILE.exists():
        raise FileExistsError(
            'Die Matches-Datei ist bereits vorhanden. '
            'Ein neuer Datenlauf muss ausdrücklich gestartet werden.'
        )

    matched_count, unmatched_count = run_pipeline()

    return {
        'initialized': True,
        'matched_count': matched_count,
        'unmatched_count': unmatched_count
    }


# ============================================================
# SAP-LERNEN
# ============================================================

def learn_sap(entry, sap_file=SAP_FILE):
    """
    Standardimplementierung:
    - bestehendes SAP-Spaltenschema beibehalten
    - Kurztext -> SAP Kurztext übernehmen
    - weitere gleichnamige Spalten übernehmen
    - Zuordnungen aus SAP_LEARNING_MAPPING berücksichtigen
    - bereits bekannten normalisierten Kurztext nicht erneut anlegen

    Falls deine bisherige learn_sap() weitere Fachregeln enthält,
    übernimm deren Funktionskörper an dieser Stelle.
    """
    sap_df = _read_csv(sap_file)

    _require_columns(
        sap_df,
        [SAP_SHORT_TEXT_COLUMN],
        'SAP-Datei'
    )

    record = dict(entry)

    short_text = str(
        record.get(SHORT_TEXT_COLUMN, '')
    ).strip()

    if not short_text:
        raise ValueError(
            'Ein Eintrag ohne Kurztext kann nicht gelernt werden.'
        )

    normalized_value = short_text.upper()

    existing_keys = _normalized_short_text(
        sap_df[SAP_SHORT_TEXT_COLUMN]
    )

    if existing_keys.eq(normalized_value).any():
        return False

    learned_record = {}

    for target_column in sap_df.columns:
        source_column = SAP_LEARNING_MAPPING.get(
            target_column,
            target_column
        )

        value = record.get(source_column, '')

        learned_record[target_column] = (
            '' if value is None else str(value)
        )

    learned_record[SAP_SHORT_TEXT_COLUMN] = short_text

    new_row = pd.DataFrame(
        [learned_record],
        columns=sap_df.columns
    )

    updated_sap_df = pd.concat(
        [sap_df, new_row],
        ignore_index=True
    )

    _write_csv_atomic(updated_sap_df, sap_file)

    return True


# ============================================================
# XML-VORLAGE UND MAPPING
# ============================================================

def _load_xml_configuration(
    template_file,
    mapping_file,
    csv_columns
):
    template_file = Path(template_file)
    mapping_file = Path(mapping_file)

    template_root = ET.parse(template_file).getroot()

    with mapping_file.open(encoding='utf-8') as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise ValueError(
            'Die XML-Mapping-Datei muss ein JSON-Objekt enthalten.'
        )

    mappings = config.get('mappings')

    if not isinstance(mappings, list) or not mappings:
        raise ValueError(
            'Die XML-Mapping-Datei benötigt eine '
            'nicht leere Liste "mappings".'
        )

    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError(
                'Jedes XML-Mapping muss ein JSON-Objekt sein.'
            )

        column = mapping.get('column')
        path = mapping.get('path')

        if not isinstance(column, str) or not column:
            raise ValueError(
                'Ein XML-Mapping enthält keinen gültigen Spaltennamen.'
            )

        if column not in csv_columns:
            raise ValueError(
                f'Die XML-Mapping-Spalte "{column}" '
                'existiert nicht in der CSV.'
            )

        if not isinstance(path, str) or not path:
            raise ValueError(
                f'Für "{column}" fehlt ein gültiger XML-Pfad.'
            )

        try:
            element = template_root.find(path)
        except (SyntaxError, KeyError) as error:
            raise ValueError(
                f'Ungültiger oder nicht unterstützter '
                f'XML-Pfad: {path}'
            ) from error

        if element is None:
            raise ValueError(
                f'Der XML-Pfad "{path}" wurde '
                'in der Vorlage nicht gefunden.'
            )

        if 'attribute' in mapping:
            attribute = mapping['attribute']

            if not isinstance(attribute, str) or not attribute:
                raise ValueError(
                    f'Ungültiger XML-Attributname für "{column}".'
                )

    return template_root, mappings


# ============================================================
# XML-EXPORT: EINE DATEI PRO MATCH
# ============================================================

def export_matches_xml(
    csv_file=MATCHED_FILE,
    export_dir=EXPORT_DIR,
    template_file=XML_TEMPLATE_FILE,
    mapping_file=XML_MAPPING_FILE
):
    csv_file = Path(csv_file).resolve()
    export_dir = Path(export_dir).resolve()

    df = _read_csv(csv_file)

    template_root, mappings = _load_xml_configuration(
        template_file=template_file,
        mapping_file=mapping_file,
        csv_columns=df.columns
    )

    export_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        'XML-Export: %s Datensätze aus %s nach %s.',
        len(df),
        csv_file,
        export_dir
    )

    exported_count = 0

    for number, record in enumerate(
        df.to_dict(orient='records'),
        start=1
    ):
        root = deepcopy(template_root)

        for mapping in mappings:
            element = root.find(mapping['path'])
            value = record[mapping['column']]

            if 'attribute' in mapping:
                element.set(
                    mapping['attribute'],
                    value
                )
            else:
                element.text = value

        tree = ET.ElementTree(root)
        ET.indent(tree, space='  ')

        xml_file = export_dir / f'match_{number:06d}.xml'
        temp_file = xml_file.with_suffix('.xml.tmp')

        try:
            tree.write(
                temp_file,
                encoding='utf-8',
                xml_declaration=True
            )

            temp_file.replace(xml_file)

        finally:
            if temp_file.exists():
                temp_file.unlink()

        exported_count += 1

        logger.info(
            'XML-Datei geschrieben: %s',
            xml_file.name
        )

    return exported_count


# ============================================================
# REVIEW: DATEN LADEN
# ============================================================

def get_review_data(
    selections=None,
    edit_index=None,
    error=None
):
    df = _read_csv(UNMATCHED_FILE)

    columns = _load_columns()
    _validate_display_columns(df, columns)

    selections = _normalize_selections(
        selections,
        len(df)
    )

    if edit_index is not None:
        edit_index = _validate_index(
            edit_index,
            len(df)
        )

    return _build_review_data(
        df=df,
        columns=columns,
        selections=selections,
        edit_index=edit_index,
        error=error
    )


# ============================================================
# REVIEW: ALLE VERWERFEN NUR MARKIEREN
# ============================================================

def select_all_discard():
    df = _read_csv(UNMATCHED_FILE)

    columns = _load_columns()
    _validate_display_columns(df, columns)

    selections = {
        f'decision_{idx}': 'discard'
        for idx in range(len(df))
    }

    return _build_review_data(
        df=df,
        columns=columns,
        selections=selections
    )


# ============================================================
# REVIEW: BEARBEITUNGSMODUS
# ============================================================

def edit_row(idx, selections=None):
    return get_review_data(
        selections=selections,
        edit_index=idx
    )


# ============================================================
# REVIEW: ERSTE ANGEZEIGTE SPALTE SPEICHERN
# ============================================================

def save_cell(idx, edited_value, selections=None):
    df = _read_csv(UNMATCHED_FILE)

    columns = _load_columns()
    _validate_display_columns(df, columns)

    idx = _validate_index(idx, len(df))

    selections = _normalize_selections(
        selections,
        len(df)
    )

    if not isinstance(edited_value, str):
        raise ValueError(
            'Der bearbeitete Wert muss als Text übergeben werden.'
        )

    edited_value = edited_value.strip()

    if not edited_value:
        return _build_review_data(
            df=df,
            columns=columns,
            selections=selections,
            edit_index=idx,
            error='Der Wert darf nicht leer sein.'
        )

    field = columns[0]['field']

    df.at[idx, field] = edited_value

    _write_csv_atomic(df, UNMATCHED_FILE)

    logger.info(
        'Zeile %s, Spalte %s gespeichert.',
        idx,
        field
    )

    return _build_review_data(
        df=df,
        columns=columns,
        selections=selections
    )


# ============================================================
# REVIEW: EINTRAGEN
# ============================================================

def apply_decisions(decisions):
    df = _read_csv(UNMATCHED_FILE)

    columns = _load_columns()
    _validate_display_columns(df, columns)

    decisions = _normalize_selections(
        decisions,
        len(df)
    )

    missing = [
        f'decision_{idx}'
        for idx in range(len(df))
        if f'decision_{idx}' not in decisions
    ]

    if missing:
        return {
            'applied': False,
            'view': _build_review_data(
                df=df,
                columns=columns,
                selections=decisions,
                error=(
                    'Bitte für jeden Eintrag '
                    'eine Entscheidung treffen.'
                )
            )
        }

    if df.empty:
        return {
            'applied': True,
            'kept_count': 0,
            'discarded_count': 0,
            'exported_count': 0
        }

    matched_df = _read_csv(MATCHED_FILE)

    if list(matched_df.columns) != list(df.columns):
        raise ValueError(
            'Matched- und Unmatched-Datei haben '
            'unterschiedliche Spalten oder Spaltenreihenfolgen.'
        )

    # XML-Vorlage und Mapping vor dem CSV-Anhängen prüfen.
    _load_xml_configuration(
        template_file=XML_TEMPLATE_FILE,
        mapping_file=XML_MAPPING_FILE,
        csv_columns=matched_df.columns
    )

    keep_indices = [
        idx
        for idx in range(len(df))
        if decisions[f'decision_{idx}'] == 'keep'
    ]

    kept_rows = df.iloc[keep_indices].copy()

    kept_count = len(kept_rows)
    discarded_count = len(df) - kept_count

    if not kept_rows.empty:
        _require_columns(
            kept_rows,
            [SHORT_TEXT_COLUMN],
            'Bestätigte Einträge'
        )

        if kept_rows[SHORT_TEXT_COLUMN].str.strip().eq('').any():
            raise ValueError(
                'Ein bestätigter Eintrag enthält keinen Kurztext.'
            )

        for _, entry in kept_rows.iterrows():
            learn_sap(
                entry,
                sap_file=SAP_FILE
            )

        kept_rows.to_csv(
            MATCHED_FILE,
            sep=CSV_SEPARATOR,
            encoding=CSV_ENCODING,
            mode='a',
            header=False,
            index=False
        )

    exported_count = export_matches_xml(
        csv_file=MATCHED_FILE,
        export_dir=EXPORT_DIR,
        template_file=XML_TEMPLATE_FILE,
        mapping_file=XML_MAPPING_FILE
    )

    # Erst nach erfolgreichem Export die Review-Liste leeren.
    _write_csv_atomic(
        df.iloc[0:0],
        UNMATCHED_FILE
    )

    logger.info(
        'Review abgeschlossen: %s behalten, '
        '%s verworfen, %s XML-Dateien exportiert.',
        kept_count,
        discarded_count,
        exported_count
    )

    return {
        'applied': True,
        'kept_count': kept_count,
        'discarded_count': discarded_count,
        'exported_count': exported_count
    }


# ============================================================
# OPTIONALE DIREKTE JSON-SCHNITTSTELLE
#
# PHP kann weiterhin bridge.py verwenden.
# Alternativ kann PHP diese app.py direkt starten.
# Beim Import werden keine Aktionen ausgeführt.
# ============================================================

def dispatch(payload):
    if not isinstance(payload, dict):
        raise ValueError(
            'Die Anfrage muss ein JSON-Objekt sein.'
        )

    action = payload.get('action')

    if action == 'initialize':
        return initialize_review()

    if action == 'review':
        return get_review_data()

    if action == 'select_all_discard':
        return select_all_discard()

    if action == 'edit_row':
        return edit_row(
            idx=payload.get('idx'),
            selections=payload.get('selections')
        )

    if action == 'save_cell':
        return save_cell(
            idx=payload.get('idx'),
            edited_value=payload.get('edited_value'),
            selections=payload.get('selections')
        )

    if action == 'apply_decisions':
        return apply_decisions(
            decisions=payload.get('decisions')
        )

    raise ValueError(
        f'Unbekannte Aktion: {action}'
    )


def main():
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO
    )

    try:
        payload = json.load(sys.stdin)

        # Diagnoseausgaben dürfen die JSON-Antwort
        # auf stdout nicht beschädigen.
        with redirect_stdout(sys.stderr):
            data = dispatch(payload)

        response = {
            'ok': True,
            'data': data
        }

        exit_code = 0

    except Exception:
        logger.exception(
            'Python-Verarbeitung fehlgeschlagen.'
        )

        response = {
            'ok': False,
            'error': 'Die Verarbeitung ist fehlgeschlagen.'
        }

        exit_code = 1

    json.dump(
        response,
        sys.stdout,
        ensure_ascii=True
    )

    sys.stdout.write('\n')

    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
