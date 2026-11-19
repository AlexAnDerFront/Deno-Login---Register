import json
import logging
import sys

from contextlib import redirect_stdout


logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO
)

# Auch versehentliche Ausgaben beim Import sollen das JSON
# auf stdout nicht beschädigen.
with redirect_stdout(sys.stderr):
    from app import (
        apply_decisions,
        edit_row,
        get_review_data,
        initialize_review,
        save_cell,
        select_all_discard,
    )


def dispatch(payload):
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
    try:
        payload = json.load(sys.stdin)

        if not isinstance(payload, dict):
            raise ValueError(
                'Die Anfrage muss ein JSON-Objekt sein.'
            )

        with redirect_stdout(sys.stderr):
            data = dispatch(payload)

        response = {
            'ok': True,
            'data': data
        }

        exit_code = 0

    except Exception:
        logging.exception(
            'Python-Verarbeitung fehlgeschlagen'
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
