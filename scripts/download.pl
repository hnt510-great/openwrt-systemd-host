#!/usr/bin/env perl
# 
# Copyright (C) 2006 OpenWrt.org
# Copyright (C) 2016 LEDE project
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#

use strict;
use warnings;
use Cwd qw(realpath);
use File::Basename;
use File::Copy;
use File::Path qw(make_path);
use File::Temp qw(tempdir);
use Fcntl qw(:flock);
use Text::ParseWords;
use JSON::PP;

@ARGV > 2 or die "Syntax: $0 <target dir> <filename> <hash> <url filename> [<mirror> ...]\n";

my $url_filename;
my $target = glob(shift @ARGV);
my $filename = shift @ARGV;
my $file_hash = shift @ARGV;
$url_filename = shift @ARGV unless $ARGV[0] =~ /:\/\//;
my $scriptdir = dirname($0);
my @mirrors;
my $ok;

my $check_certificate = $ENV{DOWNLOAD_CHECK_CERTIFICATE} eq "y";
my $custom_tool = $ENV{DOWNLOAD_TOOL_CUSTOM};
my $download_tool;

$url_filename or $url_filename = $filename;

sub localmirrors {
	my @mlist;
	open LM, "$scriptdir/localmirrors" and do {
	    while (<LM>) {
			chomp $_;
			push @mlist, $_ if $_;
		}
		close LM;
	};
	open CONFIG, "<".$ENV{'TOPDIR'}."/.config" and do {
		while (<CONFIG>) {
			/^CONFIG_LOCALMIRROR="(.+)"/ and do {
				chomp;
				my @local_mirrors = split(/;/, $1);
				push @mlist, @local_mirrors;
			};
		}
		close CONFIG;
	};

	my $mirror = $ENV{'DOWNLOAD_MIRROR'};
	$mirror and push @mlist, split(/;/, $mirror);

	return @mlist;
}

sub projectsmirrors {
	my $project = shift;
	my $append = shift;

	open (PM, "$scriptdir/projectsmirrors.json") ||
		die "Can´t open $scriptdir/projectsmirrors.json: $!\n";
	local $/;
	my $mirror_json = <PM>;
	my $mirror = decode_json $mirror_json;

	foreach (@{$mirror->{$project}}) {
		push @mirrors, $_ . "/" . ($append or "");
	}
}

sub which($) {
	my $prog = shift;
	my $res = `command -v $prog`;
	$res or return undef;
	return $res;
}

sub hash_cmd() {
	my $len = length($file_hash);
	my $cmd;

	$len == 64 and return "$ENV{'MKHASH'} sha256";
	$len == 32 and return "$ENV{'MKHASH'} md5";
	return undef;
}

sub tool_present {
	my $tool_name = shift;
	my $compare_line = shift;
	my $present = 0;

	if (open TOOL, "$tool_name --version 2>/dev/null |") {
		if (defined(my $line = readline TOOL)) {
			$present = 1 if $line =~ /^$compare_line /;
		}
		close TOOL;
	}

	return $present
}

sub select_tool {
	$custom_tool =~ tr/"//d;
	if ($custom_tool) {
		return $custom_tool;
	}

	# Try to use curl if available
	if (tool_present("curl", "curl")) {
		return "curl";
	}

	# No tool found, fallback to wget
	return "wget";
}

sub download_cmd {
	my $url = shift;
	my $filename = shift;

	if ($download_tool eq "curl") {
		return (qw(curl -f --connect-timeout 5 --retry 3 --location),
			$check_certificate ? () : '--insecure',
			shellwords($ENV{CURL_OPTIONS} || ''),
			$url);
	} elsif ($download_tool eq "wget") {
		return (qw(wget --tries=3 --timeout=5 --output-document=-),
			$check_certificate ? () : '--no-check-certificate',
			shellwords($ENV{WGET_OPTIONS} || ''),
			$url);
	} elsif ($download_tool eq "aria2c") {
		my $additional_mirrors = join(" ", map "$_/$filename", @_);
		my @chArray = ('a'..'z', 'A'..'Z', 0..9);
		my $rfn = join '', "${filename}_", map{ $chArray[int rand @chArray] } 0..9;

		@mirrors=();

		return join(" ", "[ -d $ENV{'TMPDIR'}/aria2c ] || mkdir $ENV{'TMPDIR'}/aria2c;",
			"touch $ENV{'TMPDIR'}/aria2c/${rfn}_spp;",
			qw(aria2c --stderr -c -x2 -s10 -j10 -k1M), $url, $additional_mirrors,
			$check_certificate ? () : '--check-certificate=false',
			"--server-stat-of=$ENV{'TMPDIR'}/aria2c/${rfn}_spp",
			"--server-stat-if=$ENV{'TMPDIR'}/aria2c/${rfn}_spp",
			"--daemon=false --no-conf", shellwords($ENV{ARIA2C_OPTIONS} || ''),
			"-d $ENV{'TMPDIR'}/aria2c -o $rfn;",
			"cat $ENV{'TMPDIR'}/aria2c/$rfn;",
			"rm $ENV{'TMPDIR'}/aria2c/$rfn $ENV{'TMPDIR'}/aria2c/${rfn}_spp");
	} else {
		return join(" ", $download_tool, $url);
	}
}

my $hash_cmd = hash_cmd();
$hash_cmd or ($file_hash eq "skip") or die "Cannot find appropriate hash command, ensure the provided hash is either a MD5 or SHA256 checksum.\n";

make_path($target) unless -d $target;
my $real_target = realpath($target) // $target;
my $lock;
if (($ENV{OPENWRT_DL_LOCKED} // '') ne "$real_target:$filename") {
	make_path("$real_target/.locks");
	open $lock, '>>', "$real_target/.locks/$filename" or die "Cannot open download lock: $!\n";
	flock $lock, LOCK_EX or die "Cannot lock $filename: $!\n";
}
my $work = tempdir('.download-XXXXXXXX', DIR => $real_target, CLEANUP => 1);
my $candidate = "$work/archive";

sub checksum {
	my ($path) = @_;
	my $sum;
	if ($ENV{MKHASH}) {
		open my $pipe, '-|', $ENV{MKHASH}, (length($file_hash) == 64 ? 'sha256' : 'md5'), $path
			or die "Cannot run mkhash: $!\n";
		$sum = <$pipe>;
		close $pipe or die "Could not hash $path\n";
	} else {
		my $tool = length($file_hash) == 64 ? 'sha256sum' : 'md5sum';
		open my $pipe, '-|', $tool, $path
			or die "Cannot run $tool: $!\n";
		$sum = <$pipe>;
		close $pipe or die "Could not hash $path\n";
	}
	defined $sum && $sum =~ /^(\w+)/ or die "Could not generate file hash\n";
	return $1;
}

sub download
{
	my $mirror = shift;
	my $download_filename = shift;
	my @additional_mirrors = @_;
	my @cmd;

	$mirror =~ s!/$!!;

	if ($mirror =~ s!^file://!!) {
		if (! -d "$mirror") {
			print STDERR "Wrong local cache directory -$mirror-.\n";
			cleanup();
			return;
		}

		if (! -d "$target") {
			make_path($target);
		}

		if (! open TMPDLS, "find $mirror -follow -name $filename 2>/dev/null |") {
			print("Failed to search for $filename in $mirror\n");
			return;
		}

		my $link;

		while (defined(my $line = readline TMPDLS)) {
			chomp ($link = $line);
			if ($. > 1) {
				print("$. or more instances of $filename in $mirror found . Only one instance allowed.\n");
				return;
			}
		}

		close TMPDLS;

		if (! $link) {
			print("No instances of $filename found in $mirror.\n");
			return;
		}

		print("Copying $filename from $link\n");
		copy($link, $candidate) or die "Cannot copy $link: $!\n";
	} else {
		if ($mirror =~ /a=snapshot/) {
			@cmd = download_cmd("$mirror", $download_filename, @additional_mirrors);
		} else {
			@cmd = download_cmd("$mirror/$download_filename", $download_filename, @additional_mirrors);
		}
		print STDERR "+ ".join(" ",@cmd)."\n";
		open(FETCH_FD, '-|', @cmd) or die "Cannot launch aria2c, curl or wget.\n";
		open my $output, '>', $candidate or die "Cannot create $candidate: $!\n";
		my $buffer;
		my $size;
		while ($size = read FETCH_FD, $buffer, 1048576) {
			print {$output} $buffer or die "Cannot write $candidate: $!\n";
		}
		defined $size or die "Cannot read download: $!\n";
		close $output or die "Cannot finish $candidate: $!\n";
		if (!close FETCH_FD) {
			print STDERR "Download failed.\n";
			cleanup();
			return;
		}
	}

	$hash_cmd and do {
		my $sum = checksum($candidate);

		if ($sum ne $file_hash) {
			print STDERR "Hash of the downloaded file does not match (file: $sum, requested: $file_hash) - deleting download.\n";
			cleanup();
			return;
		}
	};

	rename $candidate, "$real_target/$filename" or die "Cannot publish $filename: $!\n";
	cleanup();
}

sub cleanup
{
	unlink $candidate if defined $candidate && -e $candidate;
}

@mirrors = localmirrors();

foreach my $mirror (@ARGV) {
	if ($mirror =~ /^\@SF\/(.+)$/) {
		# give sourceforge a few more tries, because it redirects to different mirrors
		for (1 .. 5) {
			projectsmirrors '@SF', $1;
		}
	} elsif ($mirror =~ /^\@OPENWRT$/) {
		# use OpenWrt source server directly
	} elsif ($mirror =~ /^\@DEBIAN\/(.+)$/) {
		projectsmirrors '@DEBIAN', $1;
	} elsif ($mirror =~ /^\@APACHE\/(.+)$/) {
		projectsmirrors '@APACHE', $1;
	} elsif ($mirror =~ /^\@GITHUB\/(.+)$/) {
		# give github a few more tries (different mirrors)
		for (1 .. 5) {
			projectsmirrors '@GITHUB', $1;
		}
	} elsif ($mirror =~ /^\@GNU\/(.+)$/) {
		projectsmirrors '@GNU', $1;
	} elsif ($mirror =~ /^\@SAVANNAH\/(.+)$/) {
		projectsmirrors '@SAVANNAH', $1;
	} elsif ($mirror =~ /^\@KERNEL\/(.+)$/) {
		my @extra = ( $1 );
		if ($filename =~ /linux-\d+\.\d+(?:\.\d+)?-rc/) {
			push @extra, "$extra[0]/testing";
		} elsif ($filename =~ /linux-(\d+\.\d+(?:\.\d+)?)/) {
			push @extra, "$extra[0]/longterm/v$1";
		}
		foreach my $dir (@extra) {
			projectsmirrors '@KERNEL', $dir;
		}
	} elsif ($mirror =~ /^\@GNOME\/(.+)$/) {
		projectsmirrors '@GNOME', $1;
	} else {
		push @mirrors, $mirror;
	}
}

projectsmirrors '@OPENWRT';

if (-f "$real_target/$filename") {
	exit 0 unless $hash_cmd;
	my $sum = checksum("$real_target/$filename");
	exit 0 if $sum eq $file_hash;
	die "Cached $filename has hash $sum, requested $file_hash; existing archive retained.\n";
}

$download_tool = select_tool();

my $mirror = shift @mirrors;

# Try snapshot original source last
if ($mirror =~ /snapshot/) {
	push @mirrors, $mirror;
	$mirror = shift @mirrors;
}

while (!-f "$real_target/$filename") {
	$mirror or die "No more mirrors to try - giving up.\n";

	download($mirror, $url_filename, @mirrors);
	if (!-f "$real_target/$filename" && $url_filename ne $filename) {
		download($mirror, $filename, @mirrors);
	}

	$mirror = shift @mirrors;
}
