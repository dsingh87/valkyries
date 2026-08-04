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

    def test_rejects_missing_or_empty_actions(self) -> None:
        invalid_payloads = (
            {"gameId": "1022600195"},
            {"gameId": "1022600195", "actions": []},
        )

        for play_by_play in invalid_payloads:
            with self.subTest(play_by_play=play_by_play):
                with self.assertRaisesRegex(
                    PlayByPlayValidationError,
                    "actions must be a non-empty list",
                ):
                    validate_play_by_play(
                        play_by_play,
                        expected_game_id="1022600195",
                    )

    def test_rejects_duplicate_or_out_of_order_action_ids(self) -> None:
        invalid_payloads = (
            {
                "gameId": "1022600195",
                "actions": [{"actionId": 1}, {"actionId": 1}],
            },
            {
                "gameId": "1022600195",
                "actions": [{"actionId": 2}, {"actionId": 1}],
            },
        )

        for play_by_play in invalid_payloads:
            with (
                self.subTest(play_by_play=play_by_play),
                self.assertRaises(PlayByPlayValidationError),
            ):
                validate_play_by_play(
                    play_by_play,
                    expected_game_id="1022600195",
                )

    def test_reconciles_final_score(self) -> None:
        play_by_play = {
            "gameId": "1022600195",
            "actions": [
                {"actionId": 1, "scoreAway": 0, "scoreHome": 0},
                {"actionId": 2, "scoreAway": 90, "scoreHome": 82},
            ],
        }

        validate_play_by_play(
            play_by_play,
            expected_game_id="1022600195",
            expected_final_score=(90, 82),
        )

        with self.assertRaisesRegex(
            PlayByPlayValidationError,
            "does not match expected score",
        ):
            validate_play_by_play(
                play_by_play,
                expected_game_id="1022600195",
                expected_final_score=(82, 90),
            )


if __name__ == "__main__":
    unittest.main()
