import unittest

from valkyries.ingestion.wnba_play_by_play import (
    PlayByPlayValidationError,
    extract_play_by_play,
    validate_play_by_play,
)

class ExtractPlayByPlayTests(unittest.TestCase):
    def test_extracts_play_by_play_from_next_data(self) -> None:
        html = """
        <html>
          <body>
            <script id="__NEXT_DATA__" type="application/json">
              {
                "props": {
                  "pageProps": {
                    "playByPlay": {
                      "gameId": "1022600195",
                      "source": "hanaV3",
                      "actions": [
                        {
                          "actionId": 1,
                          "description": "Start of 1st Period"
                        }
                      ]
                    }
                  }
                }
              }
            </script>
          </body>
        </html>
        """

        result = extract_play_by_play(html)

        self.assertEqual(result["gameId"], "1022600195")
        self.assertEqual(result["source"], "hanaV3")
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["actionId"], 1)

class ValidatePlayByPlayTests(unittest.TestCase):
    def test_rejects_wrong_game_id(self) -> None:
        play_by_play = {
            "gameId": "wrong-game",
            "actions": [{"actionId": 1}],
        }

        with self.assertRaisesRegex(
            PlayByPlayValidationError,
            "does not match requested game 1022600195",
        ):
            validate_play_by_play(
                play_by_play,
                expected_game_id="1022600195",
            )


if __name__ == "__main__":
    unittest.main()
