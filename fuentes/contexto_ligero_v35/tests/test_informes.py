"""Verificación sintética de informes; no cuenta tokens de modelos reales."""
import unittest

from EJECUTAR_PRUEBAS import aggregate, markdown


def worker(version, measured):
    return {
        'version': version,
        'cold_scan': {'median_seconds': 1.0},
        'warm_scan': {'median_seconds': 0.1},
        'peak_process_rss_bytes': 10000,
        'database_bytes': 20000,
        'tasks': [{
            'id': 'fixture', 'query': 'fixture',
            'selection': {'precision_at_5': 0.2, 'recall_at_10': 1.0, 'reciprocal_rank': 1.0},
            'packet_recall': 1.0,
            'packet': {'characters': 30, 'estimated_tokens': 10, 'measured_tokens': measured},
            'packet_plus_same_requested_snippet': {
                'characters': 60, 'estimated_tokens': 20,
                'measured_tokens': None if measured is None else measured * 2},
            'query_timing': {'median_seconds': 0.01},
            'packet_timing': {'median_seconds': 0.02},
            'packet_budget_compliant': True, 'snippet_error': None,
        }],
    }


def report(results, repetitions=1):
    return {
        'created_utc': 'fixture', 'status': 'PASS',
        'repetitions_requested': repetitions,
        'integrity_before': {'ok': True},
        'integrity_after': {'ok': True, 'checked_files': 1},
        'commands': [], 'comparison': aggregate(results),
    }


class ReportTests(unittest.TestCase):
    def test_complete_measured_samples_are_aggregated_separately_from_estimates(self):
        result = aggregate([worker('V3.3', 12), worker('V3.3', 16)])['V3.3']
        self.assertEqual(result['total_packet_estimated_tokens'], 10)
        self.assertEqual(result['total_packet_measured_tokens'], 14)
        self.assertEqual(result['total_packet_plus_same_snippet_measured_tokens'], 28)
        self.assertEqual(result['tasks']['fixture']['packet_measured_tokens'], 14)

    def test_one_missing_measurement_keeps_all_corresponding_aggregates_null(self):
        result = aggregate([worker('V3.3', 12), worker('V3.3', None)])['V3.3']
        self.assertIsNone(result['tasks']['fixture']['packet_measured_tokens'])
        self.assertIsNone(result['total_packet_measured_tokens'])
        self.assertIsNone(result['total_packet_plus_same_snippet_measured_tokens'])
        self.assertEqual(result['total_packet_estimated_tokens'], 10)

    def test_zero_measured_tokens_is_valid_and_not_missing(self):
        result = aggregate([worker('V3.3', 0), worker('V3.3', 0)])['V3.3']
        self.assertEqual(result['total_packet_measured_tokens'], 0)

    def test_markdown_shows_actual_repetitions_and_measured_counts(self):
        text = markdown(report([worker('V3.2', 12), worker('V3.3', 9)]))
        self.assertIn('--repeticiones 1', text)
        self.assertIn('V3.2: 1; V3.3: 1', text)
        self.assertIn('| Tokens MEDIDOS de mapas (suma) | 12 | 9 |', text)
        self.assertIn('| Tokens MEDIDOS mapa + mismo snippet | 24 | 18 |', text)
        self.assertNotIn('no disponibles', text)
        self.assertNotIn('3 procesos nuevos', text)
        self.assertIn('archivos candidatos', text)

    def test_markdown_does_not_claim_measurement_when_none_exists(self):
        text = markdown(report([worker('V3.2', None), worker('V3.3', None)]))
        self.assertIn('no disponibles', text)
        self.assertNotIn('| Tokens MEDIDOS', text)

    def test_markdown_distinguishes_partial_version_measurement(self):
        text = markdown(report([worker('V3.2', 12), worker('V3.3', None)]))
        self.assertIn('Medicion de tokens incompleta', text)
        self.assertIn('| Tokens MEDIDOS de mapas (suma) | 12 | null |', text)


if __name__ == '__main__':
    unittest.main()
