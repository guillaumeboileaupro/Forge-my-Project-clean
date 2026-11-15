import unittest

from forge.filesystem.preview import MAX_FILE_BYTES, PreviewError, validate_preview


class PreviewValidationTests(unittest.TestCase):
    def setUp(self):
        self.generated = {"README.md": "origine\n", "docs/PLAN.md": "plan\n"}

    def test_accepts_text_edits_without_mutating_generated_files(self):
        edited = dict(self.generated, **{"README.md": "modifie\n"})
        result = validate_preview(edited, self.generated)
        self.assertEqual(result["README.md"], "modifie\n")
        self.assertEqual(self.generated["README.md"], "origine\n")
        self.assertEqual(list(result), ["README.md", "docs/PLAN.md"])

    def test_requires_the_exact_generated_path_set(self):
        for files in (
            {"README.md": "x"},
            dict(self.generated, **{"extra.txt": "x"}),
            {"README.md": "x", "../escape": "x"},
        ):
            with self.subTest(files=files), self.assertRaises(PreviewError):
                validate_preview(files, self.generated)

    def test_rejects_non_text_null_and_oversized_content(self):
        for content in (None, "nul\x00interdit", "x" * (MAX_FILE_BYTES + 1)):
            with self.subTest(content=type(content).__name__), self.assertRaises(PreviewError):
                validate_preview(dict(self.generated, **{"README.md": content}), self.generated)


if __name__ == "__main__":
    unittest.main()
