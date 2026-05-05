const path = require('node:path');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const prompts = require('../prompts');
const { Installer } = require('../core/installer');
const { UI } = require('../ui');
const { runUpgradeDryRun, runUpgradeYes } = require('../compiler/invoke-python');

const installer = new Installer();
const ui = new UI();

module.exports = {
  command: 'install',
  description: 'Install BMAD Core agents and tools',
  options: [
    ['-d, --debug', 'Enable debug output for manifest generation'],
    ['--directory <path>', 'Installation directory (default: current directory)'],
    ['--modules <modules>', 'Comma-separated list of module IDs to install (e.g., "bmm,bmb")'],
    [
      '--tools <tools>',
      'Comma-separated list of tool/IDE IDs to configure (e.g., "claude-code,cursor"). Use "none" to skip tool configuration.',
    ],
    ['--action <type>', 'Action type for existing installations: install, update, or quick-update'],
    ['--user-name <name>', 'Name for agents to use (default: system username)'],
    ['--communication-language <lang>', 'Language for agent communication (default: English)'],
    ['--document-output-language <lang>', 'Language for document output (default: English)'],
    ['--output-folder <path>', 'Output folder path relative to project root (default: _bmad-output)'],
    ['--custom-source <sources>', 'Comma-separated Git URLs or local paths to install custom modules from'],
    ['-y, --yes', 'Accept all defaults and skip prompts where possible'],
    [
      '--channel <channel>',
      'Apply channel (stable|next) to all external modules being installed. --all-stable and --all-next are aliases.',
    ],
    ['--all-stable', 'Alias for --channel=stable. Resolves externals to the highest stable release tag.'],
    ['--all-next', 'Alias for --channel=next. Resolves externals to main HEAD.'],
    ['--next <code>', 'Install module <code> from main HEAD (next channel). Repeatable.', (value, prev) => [...(prev || []), value], []],
    [
      '--pin <spec>',
      'Pin module to a specific tag: --pin CODE=TAG (e.g. --pin bmb=v1.7.0). Repeatable.',
      (value, prev) => [...(prev || []), value],
      [],
    ],
  ],
  action: async (options) => {
    try {
      // Set debug flag as environment variable for all components
      if (options.debug) {
        process.env.BMAD_DEBUG_MANIFEST = 'true';
        await prompts.log.info('Debug mode enabled');
      }

      // AC 4/5: detect existing bmad.lock before prompting; route to upgrade if found.
      const projectRoot = options.directory ? path.resolve(options.directory) : process.cwd();
      const lockfilePath = path.join(projectRoot, '_bmad/_config/bmad.lock');
      const lockfileExists = await fs.access(lockfilePath).then(() => true).catch(() => false);

      if (lockfileExists) {
        // Prefer installed upgrade.py; fall back to source path for dev environments.
        const installedUpgradePy = path.join(projectRoot, '_bmad', 'scripts', 'upgrade.py');
        const sourceUpgradePy = path.join(__dirname, '../../../src/scripts/upgrade.py');
        const upgradePy = fsSync.existsSync(installedUpgradePy) ? installedUpgradePy : sourceUpgradePy;

        const driftReport = await runUpgradeDryRun({ upgradePy, projectRoot });

        if (driftReport.summary.total_skills_with_drift === 0) {
          await prompts.log.info('No drift detected. Proceeding with install...');
        } else {
          const { total_skills_with_drift: n, prose_fragment_changes: m, toml_default_changes: p, glob_changes: q } = driftReport.summary;
          await prompts.log.warn(
            `Drift detected in ${n} skill(s): ${m} prose fragment(s), ${p} TOML field(s), ${q} glob input(s).`
          );

          let proceed = options.yes;
          if (!proceed) {
            const answer = await prompts.confirm({ message: 'Drift detected. Proceed with upgrade?' });
            proceed = answer;
          }

          if (proceed) {
            await prompts.log.info('Upgrading...');
            await runUpgradeYes({ upgradePy, projectRoot });
            await prompts.log.success('Upgrade complete.');
            process.exit(0);
          } else {
            await prompts.log.info('Upgrade declined. Proceeding with standard install flow...');
          }
        }
      }

      const config = await ui.promptInstall(options);

      // Handle cancel
      if (config.actionType === 'cancel') {
        await prompts.log.warn('Installation cancelled.');
        process.exit(0);
      }

      // Handle quick update separately
      if (config.actionType === 'quick-update') {
        const result = await installer.quickUpdate(config);
        await prompts.log.success('Quick update complete!');
        await prompts.log.info(`Updated ${result.moduleCount} modules with preserved settings (${result.modules.join(', ')})`);
        process.exit(0);
      }

      // Regular install/update flow
      const result = await installer.install(config);

      // Check if installation was cancelled
      if (result && result.cancelled) {
        process.exit(0);
      }

      // Check if installation succeeded
      if (result && result.success) {
        process.exit(0);
      }
    } catch (error) {
      try {
        if (error.fullMessage) {
          await prompts.log.error(error.fullMessage);
        } else {
          await prompts.log.error(`Installation failed: ${error.message}`);
        }
        if (error.stack) {
          await prompts.log.message(error.stack);
        }
      } catch {
        console.error(error.fullMessage || error.message || error);
      }
      process.exit(1);
    }
  },
};
