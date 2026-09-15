import unittest

from scripts.probe_acp_auctions import auction_ids, candidate_matches, parse_auction


class ProbeAcpAuctionsTests(unittest.TestCase):
    def test_discovers_only_supported_auction_links(self):
        html = '''
          <a href="APViewItem.asp?ID=62793">auction</a>
          <a href="/Auction/APBidHistory.asp?AucID=62794">history</a>
          <a href="APViewItem.asp?ID=bad">bad</a>
        '''
        self.assertEqual(auction_ids(html), [62794, 62793])

    def test_parses_core_fields_and_bid_table(self):
        detail = '''
          <div>Auction Title: Neopanamax Transit Slot Auction ID: 62793</div>
          <div>Closes On: 9/14/2026 3:00 PM Starting Bid: $55,000.00</div>
          <div>Transit Date: 9/18/2026 Direction: Northbound</div>
          <div>Vessel Category: Neopanamax Market Segment: LNG</div>
          <div>Vessel Name: TEST GAS IMO: 1234567</div>
        '''
        bids = '''
          <div>Final Bid Price: $385,000.00</div>
          <table><tr><th>Bidder</th><th>Amount</th></tr>
          <tr><td>CUST-1</td><td>$385,000.00</td></tr></table>
        '''
        result = parse_auction(62793, detail, bids)
        self.assertEqual(result.starting_bid_usd, 55000)
        self.assertEqual(result.final_bid_usd, 385000)
        self.assertEqual(result.direction, "Northbound")
        self.assertEqual(result.vessel_category, "Neopanamax")
        self.assertEqual(result.imo, "1234567")
        self.assertIn(["CUST-1", "$385,000.00"], result.bid_rows)

    def test_never_confirms_a_context_only_match(self):
        auction = parse_auction(
            1,
            "Transit Date: 9/18/2026 Direction: Northbound Vessel Category: Neopanamax",
            "Final Bid Price: $55,000",
        )
        vessels = [{"id": "abc", "vessel_name": "MAYBE", "direction": "Northbound"}]
        self.assertEqual(candidate_matches(auction, vessels), [])

    def test_confirms_exact_imo_only(self):
        auction = parse_auction(1, "Vessel Name: TEST GAS IMO: 1234567", "")
        matches = candidate_matches(
            auction, [{"id": "abc", "vessel_name": "Other", "imo": "1234567"}]
        )
        self.assertEqual(matches[0]["confidence"], "confirmed")
        self.assertEqual(matches[0]["reason"], "exact IMO")


if __name__ == "__main__":
    unittest.main()
