# Contributing

The holiday rules in `rules/` are maintained here, in the open. Corrections and new countries are welcome. The format is described in [docs/format.md](docs/format.md).

## Report a wrong or missing date

Open an issue with the form [Date missing or wrong](../../issues/new?template=date.yml). Give the date, where it applies and a source, ideally a link to the law or official announcement. Without a source we can't change the data.

## Fix it yourself

1. Edit the file in `rules/<COUNTRY>/`. Most changes are a rule in `public-holidays.yaml` or a period in `school-holidays/`.
2. Add an entry to `expected.yaml` that proves the change, e.g. `- { date: 2028-06-17, profile: DE-BE, holiday: gdr-uprising-anniversary }`.
3. Check it:

   ```sh
   pip install pyyaml
   python tools/check.py DE               # everything valid, every expected date holds
   python tools/check.py DE 2028 DE-BE    # what the data says for one year and profile
   ```

4. Open a pull request with the source in the description. CI runs the same check.

## Add a country

1. Open an issue with the form [Add a country](../../issues/new?template=country.yml), so nobody does the same work twice.
2. Create `rules/<CODE>/` with `country.yaml`, `public-holidays.yaml`, `expected.yaml` and a `README.md` that lists the sources. Germany in [`rules/DE`](rules/DE) is the reference.
3. Start with the public holidays. School holidays, regions and region profiles can follow in later pull requests.
4. Only use sources whose terms allow redistribution under CC BY 4.0, e.g. laws, official gazettes and open government data. Do not copy from other holiday datasets or APIs; comparing against them to find mistakes is fine.

## Review and releases

Maintainers check the source and merge. Merged data goes into the next release on `data.trakora.com`. Changes to the loaders need a passing test, see [Development](README.md#development).

## License

By contributing, you agree that your contributions to `rules/` are licensed under [CC BY 4.0](rules/LICENSE) and your contributions to code under the [MIT license](LICENSE).
